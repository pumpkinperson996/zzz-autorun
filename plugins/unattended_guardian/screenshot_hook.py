import threading
import time
from collections.abc import Callable
from datetime import datetime, timedelta
from pathlib import Path
from types import MethodType
from typing import TYPE_CHECKING, Any

from one_dragon.base.screen import screen_utils
from one_dragon.base.screen.screen_utils import FindAreaResultEnum
from one_dragon.utils import debug_utils, gpu_executor, os_utils
from one_dragon.utils.log_utils import log

from . import unattended_guardian_const as const
from .unattended_guardian_config import UnattendedGuardianConfig, get_config

if TYPE_CHECKING:
    from one_dragon.base.operation.operation import Operation
    from zzz_od.context.zzz_context import ZContext


ControllerScreenshot = Callable[..., tuple[float, Any | None]]

_CONTROLLER_HOOK_METHODS: tuple[str, ...] = (
    'screenshot',
    'get_screenshot',
    'click',
    'btn_tap',
    'btn_press',
    'drag_to',
    'scroll',
    'input_str',
    'mouse_move',
    'move_mouse_relative',
)
_OPTIONAL_CONTROLLER_HOOK_METHODS: tuple[str, ...] = ('paste_str',)
_BUTTON_CONTROLLER_HOOK_METHODS: tuple[str, ...] = ('tap', 'press', 'tap_combo')
_KEYBOARD_DEVICE_HOOK_METHODS: tuple[str, ...] = ('type',)
_CONTROLLER_REFRESH_METHODS: tuple[str, ...] = (
    'enable_keyboard',
    'enable_xbox',
    'enable_ds4',
)
_CLIPBOARD_HOOK_METHODS: tuple[str, ...] = ('copy_and_paste', 'paste_text')


def get_kicked_marker_path() -> Path:
    """返回供外部恢复脚本读取的顶号冷却标记路径。"""
    return Path(os_utils.get_path_under_work_dir('.debug', 'temp')) / const.KICKED_MARKER_FILE


def get_active_kicked_resume_at(now: datetime | None = None) -> datetime | None:
    """读取尚未到期的顶号冷却时间。"""
    path = get_kicked_marker_path()
    try:
        resume_at = datetime.strptime(path.read_text(encoding='utf-8').strip(), '%Y%m%d%H%M%S')
    except (OSError, ValueError):
        return None
    current = datetime.now() if now is None else now
    return resume_at if resume_at > current else None


class KickedPopupGuard:
    """阻断运行中顶号弹窗与未授权重登录。"""

    def __init__(
        self,
        ctx: 'ZContext',
        config: UnattendedGuardianConfig | None = None,
    ) -> None:
        self.ctx: ZContext = ctx
        self.config: UnattendedGuardianConfig = get_config() if config is None else config
        self._state_lock = threading.RLock()
        self._hook_lock = threading.Lock()
        self._input_lock = threading.RLock()
        self._input_wrapper_local = threading.local()
        self._ocr_lock = threading.Lock()
        self._sdk_log_lock = threading.Lock()
        self._operation_local = threading.local()
        self._last_check_time: float = 0
        self._last_trigger_time: float = 0
        self._hit_count: int = 0
        self._armed: bool = False
        self._login_authorized: bool = True
        self._triggered: bool = False
        self._latest_frame: Any | None = None
        self._latest_frame_time: float = 0
        self._session_process_id: int | None = None
        self._game_process_id: int | None = None
        self._capture_callback: ControllerScreenshot | None = None
        self._hooked_controller: Any | None = None
        self._hook_install_error_reported: bool = False
        self._sdk_log_path: Path = self._get_sdk_log_path()
        self._sdk_log_offset: int = 0
        self._sdk_log_remainder: bytes = b''
        self._sdk_log_initialized: bool = False
        self._sdk_log_missing_reported: bool = False
        self._monitor_stop = threading.Event()
        self._monitor_thread: threading.Thread | None = None

    @property
    def is_armed(self) -> bool:
        """返回当前游戏会话是否已禁止再次登录。"""
        with self._state_lock:
            return self._armed and not self._login_authorized

    @property
    def is_triggered(self) -> bool:
        """返回当前会话是否已经触发保护。"""
        with self._state_lock:
            return self._triggered

    def ensure_controller_hooks(self) -> bool:
        """在真实控制器出现或被替换后安装完整输入钩子。"""
        controller = getattr(self.ctx, 'controller', None)
        if controller is None:
            return False

        with self._hook_lock:
            if _controller_hooks_installed(controller, self):
                self._hooked_controller = controller
                return True

            missing_methods = [
                method_name
                for method_name in _CONTROLLER_HOOK_METHODS
                if not callable(getattr(controller, method_name, None))
            ]
            if missing_methods:
                if not self._hook_install_error_reported:
                    log.error(
                        f'[顶号检测] 控制器钩子暂不可用，缺少方法: {", ".join(missing_methods)}'
                    )
                    self._hook_install_error_reported = True
                return False

            try:
                _install_controller_hooks(controller, self)
            except Exception:
                if not self._hook_install_error_reported:
                    log.error('[顶号检测] 控制器钩子安装异常', exc_info=True)
                    self._hook_install_error_reported = True
                return False

            self._hooked_controller = controller
            self._hook_install_error_reported = False
            log.info('[顶号检测] 已绑定真实控制器的截图与输入熔断')
            return True

    def set_capture_callback(self, callback: ControllerScreenshot) -> None:
        """设置绕过守护包装的原始截图回调。"""
        self._capture_callback = callback

    def enter_operation(self, op: 'Operation') -> bool:
        """记录操作调用栈，并返回当前 Operation 是否允许执行。"""
        self.ensure_controller_hooks()
        stack = self._get_operation_stack()
        stack.append(op)
        return self.observe_operation(op)

    def exit_operation(self, op: 'Operation') -> None:
        """退出操作后恢复父操作的保护上下文。"""
        stack = self._get_operation_stack()
        authorized_ids = self._get_authorized_operation_ids()
        authorized_ids.discard(id(op))
        if stack and stack[-1] is op:
            stack.pop()
        elif op in stack:
            stack.remove(op)
        if stack:
            self.observe_operation(stack[-1])

    def observe_operation(self, op: 'Operation') -> bool:
        """根据 Operation 所属模块更新授权并返回是否允许执行。"""
        module_name = type(op).__module__
        if module_name.startswith(const.PASSIVE_OPERATION_MODULE_PREFIXES):
            return True
        if module_name.startswith(const.AUTHORIZED_LOGIN_MODULE_PREFIX):
            resume_at = get_active_kicked_resume_at()
            if resume_at is not None:
                self._block_cooldown_restart(resume_at)
                return False
            authorized_ids = self._get_authorized_operation_ids()
            if id(op) in authorized_ids:
                return True
            stack = self._get_operation_stack()
            inherited = any(
                candidate is not op and id(candidate) in authorized_ids
                for candidate in stack
            )
            if inherited:
                authorized_ids.add(id(op))
                return True
            if module_name.startswith(
                const.TRUSTED_ACCOUNT_SWITCH_MODULE_PREFIX
            ):
                allowed = self._authorize_trusted_account_switch()
            else:
                allowed = self._authorize_login_for_new_process()
            if allowed and op in stack:
                authorized_ids.add(id(op))
            return allowed
        self.arm()
        return True

    def arm(self) -> None:
        """在进入非登录流程后武装当前游戏会话。"""
        with self._state_lock:
            if self._triggered or self._is_protected_session():
                return

        self._discard_existing_sdk_log()
        process_id = self._get_game_process_id()
        with self._state_lock:
            if self._triggered or self._is_protected_session():
                return
            self._armed = True
            self._login_authorized = False
            if process_id is not None:
                self._game_process_id = process_id
                self._session_process_id = process_id

    def on_frame(self, screenshot: Any, force_ocr: bool = False) -> None:
        """检查控制器产生的一帧截图。

        Args:
            screenshot: 1080p 游戏截图。
            force_ocr: 是否忽略普通 OCR 节流，用于输入前检查。
        """
        if screenshot is None or not self.config.detect_enabled:
            return

        self._refresh_game_process()
        now = time.time()
        with self._state_lock:
            self._latest_frame = screenshot
            self._latest_frame_time = now

        if not self._is_protected_session():
            return

        try:
            is_login_screen = self._is_login_screen(screenshot)
        except Exception:
            log.error('[顶号检测] 登录页模板检测异常，按失败关闭处理', exc_info=True)
            self._on_kicked('登录页模板检测异常，已按失败关闭阻断输入')
            return

        if is_login_screen:
            self._on_kicked('运行中返回登录页，已阻断自动重登录')
            return

        try:
            self._check_popup_if_due(screenshot, now, force_ocr)
        except Exception:
            log.error('[顶号检测] 顶号弹窗 OCR 异常', exc_info=True)
            if force_ocr:
                self._on_kicked('输入前顶号弹窗检测异常，已按失败关闭阻断输入')

    def before_input(
        self,
        action_name: str,
        force_ocr: bool = False,
        require_fresh: bool = True,
    ) -> bool:
        """在自动输入前执行失败关闭检查。

        Args:
            action_name: 输入动作名，用于日志定位。
            force_ocr: 是否强制执行弹窗 OCR。
            require_fresh: 是否必须独立获取当前帧，不复用历史截图。

        Returns:
            True 表示允许原始输入，False 表示必须阻断。
        """
        with self._input_lock:
            self._refresh_game_process()
            if not self.config.detect_enabled or not self._is_protected_session():
                return not self.is_triggered

            screenshot = self._get_recent_or_fresh_frame(require_fresh)
            if screenshot is None:
                log.error(f'[顶号检测] 输入前安全截图失败，阻断动作: {action_name}')
                self._on_kicked(f'输入前安全截图失败，已阻断动作 {action_name}')
                return False

            self.on_frame(screenshot, force_ocr=force_ocr)
            if self.is_triggered:
                log.error(f'[顶号检测] 危险界面输入已阻断: {action_name}')
                return False
            return True

    def run_guarded_input(
        self,
        action_name: str,
        callback: Callable[[], Any],
        *,
        force_ocr: bool = False,
        require_fresh: bool = True,
        blocked_result: Any = None,
    ) -> Any:
        """只在最外层输入入口执行检查，并让同一动作的底层调用复用结果。"""
        depth = getattr(self._input_wrapper_local, 'depth', 0)
        if depth > 0:
            return callback()
        if not self.before_input(
            action_name,
            force_ocr=force_ocr,
            require_fresh=require_fresh,
        ):
            return blocked_result

        self._input_wrapper_local.depth = depth + 1
        try:
            return callback()
        finally:
            self._input_wrapper_local.depth = depth

    def start_sdk_log_monitor(self) -> None:
        """启动登录 SDK 日志的独立增量监听。"""
        if self._monitor_thread is not None and self._monitor_thread.is_alive():
            return
        self._monitor_stop.clear()
        self._initialize_sdk_log_offset()
        self._monitor_thread = threading.Thread(
            target=self._sdk_log_monitor_loop,
            name='unattended_guardian_sdk_log',
            daemon=True,
        )
        self._monitor_thread.start()

    def stop_sdk_log_monitor(self) -> None:
        """停止当前守护实例的 SDK 日志监听。"""
        self._monitor_stop.set()

    def handle_sdk_log_line(self, line: str) -> None:
        """处理一行 SDK 日志，命中二次登录信号时熔断。"""
        if not self._is_protected_session():
            return
        if any(marker in line for marker in const.SDK_RELOGIN_LOG_MARKERS):
            self._on_kicked('运行中登录 SDK 再次初始化，已阻断自动重登录')

    def _get_operation_stack(self) -> list['Operation']:
        """返回当前线程的 Operation 调用栈。"""
        stack = getattr(self._operation_local, 'stack', None)
        if stack is None:
            stack = []
            self._operation_local.stack = stack
        return stack

    def _get_authorized_operation_ids(self) -> set[int]:
        """返回当前线程已经授权的登录 Operation 标识。"""
        authorized_ids = getattr(self._operation_local, 'authorized_ids', None)
        if authorized_ids is None:
            authorized_ids = set()
            self._operation_local.authorized_ids = authorized_ids
        return authorized_ids

    def _authorize_login_for_new_process(self) -> bool:
        """仅允许首次登录或旧会话已经退出后的新进程登录。"""
        resume_at = get_active_kicked_resume_at()
        if resume_at is not None:
            self._block_cooldown_restart(resume_at)
            return False

        process_id = self._get_game_process_id()
        with self._state_lock:
            protected = self._armed and not self._login_authorized
            triggered = self._triggered
            session_process_id = self._session_process_id

        old_process_exited = (
            process_id is None
            and (
                session_process_id is None
                or not self._is_process_alive(session_process_id)
            )
        )
        different_process = (
            process_id is not None
            and (
                session_process_id is None
                or process_id != session_process_id
            )
        )
        if (protected or triggered) and not (
            old_process_exited or different_process
        ):
            self._on_kicked('运行中的同一游戏进程进入登录流程，已拒绝再次授权')
            return False

        self._grant_login_authorization(process_id)
        return True

    def _authorize_trusted_account_switch(self) -> bool:
        """允许一条龙明确编排的同进程切换账号流程。"""
        resume_at = get_active_kicked_resume_at()
        if resume_at is not None:
            self._block_cooldown_restart(resume_at)
            return False

        process_id = self._get_game_process_id()
        self._grant_login_authorization(process_id)
        log.info('[顶号检测] 已授权一条龙显式切换账号')
        return True

    def _grant_login_authorization(self, process_id: int | None) -> None:
        """重置事故状态并授予当前明确登录作用域一次授权。"""
        with self._state_lock:
            self._armed = False
            self._login_authorized = True
            self._triggered = False
            self._hit_count = 0
            self._last_check_time = 0
            self._session_process_id = None
            self._game_process_id = process_id
        self._discard_existing_sdk_log()

    def _block_cooldown_restart(self, resume_at: datetime) -> None:
        """阻止冷却期内绕过外部恢复脚本重新登录。"""
        with self._state_lock:
            self._triggered = True
            self._armed = True
            self._login_authorized = False

        log.error(
            f'[顶号检测] 顶号冷却尚未结束，拒绝重新登录；最早恢复时间 '
            f'{resume_at.strftime("%Y-%m-%d %H:%M:%S")}'
        )
        try:
            controller = getattr(self.ctx, 'controller', None)
            if controller is not None:
                controller.close_game()
        except Exception:
            log.error('[顶号检测] 冷却期关闭游戏失败', exc_info=True)
        try:
            self.ctx.run_context.stop_running()
        except Exception:
            log.error('[顶号检测] 冷却期停止一条龙失败', exc_info=True)

    def _is_protected_session(self) -> bool:
        """返回当前是否应当拦截任何登录行为。"""
        with self._state_lock:
            return self._armed and not self._login_authorized and not self._triggered

    def _get_recent_or_fresh_frame(self, require_fresh: bool) -> Any | None:
        """按安全等级复用最新帧或通过原始控制器独立截图。"""
        now = time.time()
        with self._state_lock:
            if (
                not require_fresh
                and self._latest_frame is not None
                and now - self._latest_frame_time <= const.INPUT_FRAME_MAX_AGE_SECONDS
            ):
                return self._latest_frame

        if self._capture_callback is None:
            return None
        try:
            _, screenshot = self._capture_callback(independent=True)
            return screenshot
        except Exception:
            log.error('[顶号检测] 输入前独立截图异常', exc_info=True)
            return None

    def _is_login_screen(self, screenshot: Any) -> bool:
        """使用多个稳定模板快速判断是否回到登录页。"""
        hit_count = 0
        for area_name in const.LOGIN_SCREEN_TEMPLATE_AREAS:
            area = self.ctx.screen_loader.get_area(const.LOGIN_SCREEN_NAME, area_name)
            if area is None or not area.is_template_area:
                continue
            result = screen_utils.find_area_in_screen(self.ctx, screenshot, area)
            if result == FindAreaResultEnum.TRUE:
                hit_count += 1
                if hit_count >= const.LOGIN_SCREEN_REQUIRED_TEMPLATE_HITS:
                    return True
        return False

    def _check_popup_if_due(self, screenshot: Any, now: float, force_ocr: bool) -> None:
        """在节流允许时执行顶号弹窗 OCR。"""
        with self._state_lock:
            if (
                not force_ocr
                and now - self._last_check_time < self.config.check_interval_seconds
            ):
                return

        acquired = self._ocr_lock.acquire(blocking=force_ocr)
        if not acquired:
            return
        try:
            with self._state_lock:
                if not self._is_protected_session():
                    return
                if (
                    not force_ocr
                    and now - self._last_check_time < self.config.check_interval_seconds
                ):
                    return
                self._last_check_time = now
            self._check_popup(screenshot, now)
        finally:
            self._ocr_lock.release()

    def _check_popup(self, screenshot: Any, now: float) -> None:
        """对中央区域做 OCR，命中关键词后处理顶号事件。"""
        x1, y1, x2, y2 = const.POPUP_CROP_RECT
        crop = screenshot[y1:y2, x1:x2]

        ocr_result_map = gpu_executor.run_sync(self.ctx.ocr.run_ocr, crop)
        text = ''.join(ocr_result_map.keys())
        normalized_text = ''.join(text.split())

        hit = any(keyword in normalized_text for keyword in self.config.kicked_keywords)
        if hit:
            self._hit_count += 1
            log.warning(
                f'[顶号检测] 疑似顶号弹窗，第 {self._hit_count} 次命中: '
                f'{normalized_text[:50]}'
            )
        else:
            self._hit_count = 0

        if self._hit_count < const.KICKED_CONFIRM_HITS:
            return
        self._hit_count = 0

        if now - self._last_trigger_time < const.KICKED_TRIGGER_COOLDOWN_SECONDS:
            return
        self._last_trigger_time = now
        self._on_kicked(normalized_text)

    def _on_kicked(self, text: str) -> None:
        """记录冷却、留存证据、通知用户并关闭游戏。"""
        with self._state_lock:
            if self._triggered:
                return
            self._triggered = True
            self._armed = True
            self._login_authorized = False
            screenshot = self._latest_frame

        resume_at = datetime.now() + timedelta(minutes=self.config.kicked_cooldown_minutes)
        self._write_kicked_marker(resume_at)
        evidence_name = self._save_evidence(screenshot)
        log.error(f'[顶号检测] 判定账号被顶号或发生未授权重登录，停止一条龙: {text[:100]}')
        if evidence_name:
            log.error(f'[顶号检测] 证据截图已保存: .debug/images/{evidence_name}.png')

        try:
            self.ctx.push_service.push_async(
                title='检测到账号被顶号或重登录',
                content=(
                    '已阻断输入、停止一条龙并关闭游戏，不会继续自动登录。'
                    f'外部恢复脚本最早将在 {resume_at.strftime("%Y-%m-%d %H:%M")} 后继续。'
                ),
            )
        except Exception:
            log.error('[顶号检测] 通知推送失败', exc_info=True)

        try:
            controller = getattr(self.ctx, 'controller', None)
            if controller is not None:
                controller.close_game()
            log.info('[顶号检测] 已关闭游戏')
        except Exception:
            log.error('[顶号检测] 关闭游戏失败', exc_info=True)

        try:
            self.ctx.run_context.stop_running()
        except Exception:
            log.error('[顶号检测] 停止一条龙失败', exc_info=True)

    def _save_evidence(self, screenshot: Any | None) -> str:
        """保存触发保护时的画面。"""
        if screenshot is None:
            return ''
        try:
            return debug_utils.save_debug_image(
                screenshot,
                prefix='UnattendedGuardian',
            )
        except Exception:
            log.error('[顶号检测] 保存证据截图失败', exc_info=True)
            return ''

    @staticmethod
    def _write_kicked_marker(resume_at: datetime) -> None:
        """写入 AHK 可直接解析的本地时间戳。"""
        try:
            path = get_kicked_marker_path()
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(resume_at.strftime('%Y%m%d%H%M%S'), encoding='utf-8')
        except Exception:
            log.error('[顶号检测] 冷却标记写入失败', exc_info=True)

    @staticmethod
    def _get_sdk_log_path() -> Path:
        """返回国服登录 SDK 日志路径。"""
        return (
            Path.home()
            / 'AppData'
            / 'LocalLow'
            / 'miHoYo'
            / '绝区零'
            / 'logs'
            / 'MiHoYoSDK.log'
        )

    def _initialize_sdk_log_offset(self) -> None:
        """从日志末尾开始监听，忽略安装守护前的历史记录。"""
        with self._sdk_log_lock:
            try:
                self._sdk_log_offset = self._sdk_log_path.stat().st_size
                self._sdk_log_initialized = True
            except OSError:
                self._sdk_log_offset = 0
                self._sdk_log_initialized = False
            self._sdk_log_remainder = b''

    def _discard_existing_sdk_log(self) -> None:
        """切换保护阶段时丢弃此前授权登录产生的 SDK 日志。"""
        with self._sdk_log_lock:
            try:
                self._sdk_log_offset = self._sdk_log_path.stat().st_size
                self._sdk_log_initialized = True
            except OSError:
                self._sdk_log_offset = 0
                self._sdk_log_initialized = False
            self._sdk_log_remainder = b''

    def _sdk_log_monitor_loop(self) -> None:
        """轮询增量 SDK 日志，作为画面检测之外的独立防线。"""
        while not self._monitor_stop.wait(const.SDK_LOG_POLL_SECONDS):
            if not _is_active_guard(self):
                return
            self.ensure_controller_hooks()
            self._refresh_game_process()
            self._read_new_sdk_log_lines()

    def _read_new_sdk_log_lines(self) -> None:
        """读取 SDK 日志新增内容。"""
        lines: list[str] = []
        with self._sdk_log_lock:
            if not self._sdk_log_path.exists():
                self._sdk_log_initialized = False
                self._sdk_log_offset = 0
                self._sdk_log_remainder = b''
                if not self._sdk_log_missing_reported:
                    log.warning(
                        f'[顶号检测] SDK 日志不存在，日志兜底暂不可用: '
                        f'{self._sdk_log_path}'
                    )
                    self._sdk_log_missing_reported = True
                return

            try:
                size = self._sdk_log_path.stat().st_size
                if not self._sdk_log_initialized:
                    self._sdk_log_offset = size
                    self._sdk_log_initialized = True
                    self._sdk_log_missing_reported = False
                    return
                if size < self._sdk_log_offset:
                    self._sdk_log_offset = 0
                    self._sdk_log_remainder = b''

                with self._sdk_log_path.open('rb') as log_file:
                    log_file.seek(self._sdk_log_offset)
                    new_content = log_file.read()
                    self._sdk_log_offset = log_file.tell()
                self._sdk_log_missing_reported = False
            except OSError:
                log.error(
                    '[顶号检测] 读取 SDK 日志失败，保留截图与输入防线',
                    exc_info=True,
                )
                return

            if not new_content:
                return
            content = self._sdk_log_remainder + new_content
            raw_lines = content.splitlines(keepends=True)
            if raw_lines and not raw_lines[-1].endswith((b'\n', b'\r')):
                self._sdk_log_remainder = raw_lines.pop()
            else:
                self._sdk_log_remainder = b''
            lines = [raw_line.decode('utf-8', errors='ignore') for raw_line in raw_lines]

        if not self._is_protected_session():
            return
        for line in lines:
            self.handle_sdk_log_line(line)

    def _refresh_game_process(self) -> None:
        """跟踪进程变化，但只允许明确的 EnterGame 流程重新授权。"""
        process_id = self._get_game_process_id()
        changed_message = ''
        with self._state_lock:
            previous_process_id = self._game_process_id
            if process_id is None:
                if previous_process_id is not None:
                    self._latest_frame = None
                    self._latest_frame_time = 0
                self._game_process_id = None
                return
            if process_id == previous_process_id:
                return

            self._game_process_id = process_id
            self._latest_frame = None
            self._latest_frame_time = 0
            if previous_process_id is None:
                if (
                    self._session_process_id is not None
                    and process_id != self._session_process_id
                ):
                    changed_message = (
                        f'[顶号检测] 检测到新游戏进程 {process_id}，'
                        '保持熔断，等待明确的初始登录流程'
                    )
            else:
                changed_message = (
                    f'[顶号检测] 游戏进程由 {previous_process_id} 变为 {process_id}，'
                    '不会自动解除登录熔断'
                )
            if self._armed or self._triggered:
                self._armed = True
                self._login_authorized = False
            if (
                self._armed
                and not self._triggered
                and self._session_process_id is None
            ):
                self._session_process_id = process_id

        if changed_message:
            log.warning(changed_message)

    def _get_game_process_id(self) -> int | None:
        """读取当前游戏窗口所属进程 ID。"""
        controller = getattr(self.ctx, 'controller', None)
        game_win = getattr(controller, 'game_win', None)
        if game_win is None:
            return None
        try:
            import win32gui
            import win32process

            hwnd = game_win.get_hwnd()
            if hwnd is None:
                return None
            if not win32gui.IsWindow(hwnd):
                refresh_win = getattr(game_win, 'refresh_win', None)
                if callable(refresh_win):
                    refresh_win()
                hwnd = game_win.get_hwnd()
            if hwnd is None or not win32gui.IsWindow(hwnd):
                return None
            _, process_id = win32process.GetWindowThreadProcessId(hwnd)
            parsed_process_id = int(process_id)
            return parsed_process_id if parsed_process_id > 0 else None
        except Exception:
            return None

    @staticmethod
    def _is_process_alive(process_id: int) -> bool:
        """失败关闭地确认旧会话 PID 是否仍然存在。"""
        if process_id <= 0:
            return False
        try:
            import psutil

            return psutil.Process(process_id).is_running()
        except psutil.NoSuchProcess:
            return False
        except psutil.Error:
            return True


_active_guard_lock = threading.Lock()
_active_guard: KickedPopupGuard | None = None


def install_hook(ctx: 'ZContext') -> bool:
    """安装 Operation 生命周期、控制器输入与 SDK 日志熔断钩子。"""
    global _active_guard
    try:
        from one_dragon.base.operation.operation import Operation

        guard = KickedPopupGuard(ctx)
        _install_operation_hooks(Operation, guard)
        _install_clipboard_hooks(guard)

        with _active_guard_lock:
            previous_guard = _active_guard
            _active_guard = guard
        if previous_guard is not None:
            previous_guard.stop_sdk_log_monitor()

        controller_ready = guard.ensure_controller_hooks()
        guard.start_sdk_log_monitor()
        if controller_ready:
            log.info('[顶号检测] Operation、控制器输入与 SDK 日志钩子安装成功')
        else:
            log.info('[顶号检测] Operation 与 SDK 钩子已安装，等待真实控制器初始化')
        return True
    except Exception:
        log.error('[顶号检测] 钩子安装异常，插件功能停用', exc_info=True)
        return False


def ensure_hook_installed(ctx: 'ZContext') -> bool:
    """确保当前上下文与当前真实控制器都已安装完整钩子。"""
    guard = get_guard()
    if guard is None or guard.ctx is not ctx:
        if not install_hook(ctx):
            return False
        guard = get_guard()
    if guard is None:
        return False

    try:
        from one_dragon.base.operation.operation import Operation

        if not _operation_hooks_installed(Operation, guard):
            _install_operation_hooks(Operation, guard)
        if not _clipboard_hooks_installed(guard):
            _install_clipboard_hooks(guard)
    except Exception:
        log.error('[顶号检测] Operation 钩子补装失败', exc_info=True)
        return False
    return guard.ensure_controller_hooks() and is_hook_installed()


def _install_operation_hooks(operation_class: type, guard: KickedPopupGuard) -> None:
    """包装 Operation 执行与截图，维护嵌套登录授权上下文。"""
    current_execute = operation_class.execute
    original_execute = _unwrap_method(current_execute)
    current_screenshot = operation_class.screenshot
    original_screenshot = _unwrap_method(current_screenshot)

    def execute_with_guard(op_self: 'Operation') -> Any:
        allowed = guard.enter_operation(op_self)
        try:
            if not allowed:
                return op_self.op_fail(const.LOGIN_BLOCKED_STATUS)
            return original_execute(op_self)
        finally:
            guard.exit_operation(op_self)

    def screenshot_with_guard(op_self: 'Operation') -> Any:
        guard.ensure_controller_hooks()
        guard.observe_operation(op_self)
        return original_screenshot(op_self)

    for wrapper, original in (
        (execute_with_guard, original_execute),
        (screenshot_with_guard, original_screenshot),
    ):
        wrapper.__name__ = original.__name__
        wrapper.__doc__ = original.__doc__
        wrapper._kicked_guard_original = original
        wrapper._kicked_guard_owner = guard

    operation_class.execute = execute_with_guard
    operation_class.screenshot = screenshot_with_guard


def _install_controller_hooks(controller: Any, guard: KickedPopupGuard) -> None:
    """包装控制器截图、公共输入与可被业务代码直接访问的底层输入。"""
    original_screenshot = _unwrap_method(controller.screenshot)
    original_get_screenshot = _unwrap_method(controller.get_screenshot)
    original_click = _unwrap_method(controller.click)
    original_btn_tap = _unwrap_method(controller.btn_tap)
    original_btn_press = _unwrap_method(controller.btn_press)
    original_drag_to = _unwrap_method(controller.drag_to)
    original_scroll = _unwrap_method(controller.scroll)
    original_input_str = _unwrap_method(controller.input_str)
    paste_str = getattr(controller, 'paste_str', None)
    original_paste_str = _unwrap_method(paste_str) if callable(paste_str) else None
    original_mouse_move = _unwrap_method(controller.mouse_move)
    original_move_mouse_relative = _unwrap_method(controller.move_mouse_relative)
    guard.set_capture_callback(original_screenshot)

    def screenshot_with_guard(
        controller_self: Any,
        independent: bool = False,
    ) -> tuple[float, Any | None]:
        result = original_screenshot(independent=independent)
        guard.on_frame(result[1])
        return result

    def get_screenshot_with_guard(
        controller_self: Any,
        independent: bool = False,
    ) -> Any:
        result = original_get_screenshot(independent=independent)
        guard.on_frame(result)
        return result

    def click_with_guard(
        controller_self: Any,
        pos: Any = None,
        press_time: float = 0.1,
        pc_alt: bool = False,
        gamepad_key: str | None = None,
    ) -> bool:
        return guard.run_guarded_input(
            'click',
            lambda: original_click(
                pos=pos,
                press_time=press_time,
                pc_alt=pc_alt,
                gamepad_key=gamepad_key,
            ),
            force_ocr=True,
            require_fresh=True,
            blocked_result=False,
        )

    def btn_tap_with_guard(controller_self: Any, key: str) -> None:
        guard.run_guarded_input(
            f'btn_tap:{key}',
            lambda: original_btn_tap(key),
            require_fresh=True,
        )

    def btn_press_with_guard(
        controller_self: Any,
        key: str,
        press_time: float | None = None,
    ) -> None:
        guard.run_guarded_input(
            f'btn_press:{key}',
            lambda: original_btn_press(key, press_time),
            require_fresh=True,
        )

    def drag_to_with_guard(
        controller_self: Any,
        end: Any,
        start: Any | None = None,
        duration: float = 0.5,
    ) -> None:
        guard.run_guarded_input(
            'drag_to',
            lambda: original_drag_to(end=end, start=start, duration=duration),
            force_ocr=True,
            require_fresh=True,
        )

    def scroll_with_guard(
        controller_self: Any,
        down: int,
        pos: Any | None = None,
    ) -> None:
        guard.run_guarded_input(
            'scroll',
            lambda: original_scroll(down=down, pos=pos),
            force_ocr=True,
            require_fresh=True,
        )

    def input_str_with_guard(
        controller_self: Any,
        to_input: str,
        interval: float = 0.1,
    ) -> None:
        guard.run_guarded_input(
            'input_str',
            lambda: original_input_str(to_input=to_input, interval=interval),
            force_ocr=True,
            require_fresh=True,
        )

    def paste_str_with_guard(controller_self: Any, to_input: str) -> None:
        if original_paste_str is None:
            return
        guard.run_guarded_input(
            'paste_str',
            lambda: original_paste_str(to_input),
            force_ocr=True,
            require_fresh=True,
        )

    def mouse_move_with_guard(controller_self: Any, game_pos: Any) -> None:
        guard.run_guarded_input(
            'mouse_move',
            lambda: original_mouse_move(game_pos),
            require_fresh=False,
        )

    def move_mouse_relative_with_guard(
        controller_self: Any,
        dx: float,
        dy: float,
    ) -> None:
        guard.run_guarded_input(
            'move_mouse_relative',
            lambda: original_move_mouse_relative(dx, dy),
            require_fresh=False,
        )

    wrappers: list[tuple[str, Callable[..., Any], Callable[..., Any]]] = [
        ('screenshot', screenshot_with_guard, original_screenshot),
        ('get_screenshot', get_screenshot_with_guard, original_get_screenshot),
        ('click', click_with_guard, original_click),
        ('btn_tap', btn_tap_with_guard, original_btn_tap),
        ('btn_press', btn_press_with_guard, original_btn_press),
        ('drag_to', drag_to_with_guard, original_drag_to),
        ('scroll', scroll_with_guard, original_scroll),
        ('input_str', input_str_with_guard, original_input_str),
        ('mouse_move', mouse_move_with_guard, original_mouse_move),
        (
            'move_mouse_relative',
            move_mouse_relative_with_guard,
            original_move_mouse_relative,
        ),
    ]
    if original_paste_str is not None:
        wrappers.append(('paste_str', paste_str_with_guard, original_paste_str))
    for method_name, wrapper, original in wrappers:
        wrapper._kicked_guard_original = original
        wrapper._kicked_guard_owner = guard
        setattr(controller, method_name, MethodType(wrapper, controller))

    for method_name in _CONTROLLER_REFRESH_METHODS:
        current = getattr(controller, method_name, None)
        if not callable(current):
            continue
        original = _unwrap_method(current)

        def refresh_with_guard(
            controller_self: Any,
            *args: Any,
            _original: Callable[..., Any] = original,
            **kwargs: Any,
        ) -> Any:
            result = _original(*args, **kwargs)
            guard.ensure_controller_hooks()
            return result

        refresh_with_guard._kicked_guard_original = original
        refresh_with_guard._kicked_guard_owner = guard
        setattr(controller, method_name, MethodType(refresh_with_guard, controller))

    for button_controller in _get_button_controller_targets(controller):
        _install_button_controller_hooks(button_controller, guard)

    keyboard_controller = getattr(controller, 'keyboard_controller', None)
    keyboard_device = getattr(keyboard_controller, 'keyboard', None)
    if keyboard_device is not None:
        _install_keyboard_device_hooks(keyboard_device, guard)


def _install_button_controller_hooks(
    button_controller: Any,
    guard: KickedPopupGuard,
) -> None:
    """覆盖键鼠、Xbox 与 DS4 控制器可被直接调用的输入方法。"""
    original_tap = _unwrap_method(button_controller.tap)
    original_press = _unwrap_method(button_controller.press)
    original_tap_combo = _unwrap_method(button_controller.tap_combo)

    def tap_with_guard(button_self: Any, key: str) -> None:
        guard.run_guarded_input(
            f'button.tap:{key}',
            lambda: original_tap(key),
            require_fresh=True,
        )

    def press_with_guard(
        button_self: Any,
        key: str,
        press_time: float | None = None,
    ) -> None:
        guard.run_guarded_input(
            f'button.press:{key}',
            lambda: original_press(key, press_time),
            require_fresh=True,
        )

    def tap_combo_with_guard(button_self: Any, keys: list[str]) -> None:
        guard.run_guarded_input(
            'button.tap_combo',
            lambda: original_tap_combo(keys),
            require_fresh=True,
        )

    for method_name, wrapper, original in (
        ('tap', tap_with_guard, original_tap),
        ('press', press_with_guard, original_press),
        ('tap_combo', tap_combo_with_guard, original_tap_combo),
    ):
        wrapper._kicked_guard_original = original
        wrapper._kicked_guard_owner = guard
        setattr(
            button_controller,
            method_name,
            MethodType(wrapper, button_controller),
        )


def _install_keyboard_device_hooks(
    keyboard_device: Any,
    guard: KickedPopupGuard,
) -> None:
    """覆盖业务代码直接使用的 pynput 文本输入入口。"""
    original_type = _unwrap_method(keyboard_device.type)

    def type_with_guard(keyboard_self: Any, text: str) -> None:
        guard.run_guarded_input(
            'keyboard.type',
            lambda: original_type(text),
            force_ocr=True,
            require_fresh=True,
        )

    type_with_guard._kicked_guard_original = original_type
    type_with_guard._kicked_guard_owner = guard
    keyboard_device.type = MethodType(type_with_guard, keyboard_device)


def _install_clipboard_hooks(guard: KickedPopupGuard) -> None:
    """覆盖静态剪贴板粘贴入口，防止绕过控制器文本输入钩子。"""
    from one_dragon.base.controller.pc_clipboard import PcClipboard

    original_copy_and_paste = _unwrap_method(PcClipboard.copy_and_paste)
    original_paste_text = _unwrap_method(PcClipboard.paste_text)

    def copy_and_paste_with_guard(text: str) -> None:
        guard.run_guarded_input(
            'clipboard.copy_and_paste',
            lambda: original_copy_and_paste(text),
            force_ocr=True,
            require_fresh=True,
        )

    def paste_text_with_guard() -> str:
        return guard.run_guarded_input(
            'clipboard.paste_text',
            original_paste_text,
            force_ocr=True,
            require_fresh=True,
            blocked_result='',
        )

    for method_name, wrapper, original in (
        ('copy_and_paste', copy_and_paste_with_guard, original_copy_and_paste),
        ('paste_text', paste_text_with_guard, original_paste_text),
    ):
        wrapper._kicked_guard_original = original
        wrapper._kicked_guard_owner = guard
        setattr(PcClipboard, method_name, staticmethod(wrapper))


def _unwrap_method(method: Callable[..., Any]) -> Callable[..., Any]:
    """获取可能已被守护包装的方法原始版本。"""
    return getattr(method, '_kicked_guard_original', method)


def _operation_hooks_installed(
    operation_class: type,
    guard: KickedPopupGuard,
) -> bool:
    """返回 Operation 生命周期钩子是否属于指定守护实例。"""
    return all(
        getattr(method, '_kicked_guard_owner', None) is guard
        for method in (
            operation_class.execute,
            operation_class.screenshot,
        )
    )


def _get_button_controller_targets(controller: Any) -> list[Any]:
    """返回当前控制器持有的全部不重复底层按键控制器。"""
    targets: list[Any] = []
    target_ids: set[int] = set()
    for attr_name in (
        'btn_controller',
        'keyboard_controller',
        'xbox_controller',
        'ds4_controller',
    ):
        target = getattr(controller, attr_name, None)
        if target is None or id(target) in target_ids:
            continue
        if not all(
            callable(getattr(target, method_name, None))
            for method_name in _BUTTON_CONTROLLER_HOOK_METHODS
        ):
            continue
        target_ids.add(id(target))
        targets.append(target)
    return targets


def _controller_hooks_installed(
    controller: Any,
    guard: KickedPopupGuard,
) -> bool:
    """返回控制器完整钩子是否属于指定守护实例。"""
    method_names = list(_CONTROLLER_HOOK_METHODS)
    method_names.extend(
        method_name
        for method_name in _OPTIONAL_CONTROLLER_HOOK_METHODS
        if callable(getattr(controller, method_name, None))
    )
    method_names.extend(
        method_name
        for method_name in _CONTROLLER_REFRESH_METHODS
        if callable(getattr(controller, method_name, None))
    )
    public_hooks_ready = all(
        getattr(getattr(controller, method_name, None), '_kicked_guard_owner', None)
        is guard
        for method_name in method_names
    )
    if not public_hooks_ready:
        return False

    for button_controller in _get_button_controller_targets(controller):
        if not all(
            getattr(
                getattr(button_controller, method_name, None),
                '_kicked_guard_owner',
                None,
            )
            is guard
            for method_name in _BUTTON_CONTROLLER_HOOK_METHODS
        ):
            return False

    keyboard_controller = getattr(controller, 'keyboard_controller', None)
    keyboard_device = getattr(keyboard_controller, 'keyboard', None)
    if keyboard_device is not None:
        if not all(
            getattr(
                getattr(keyboard_device, method_name, None),
                '_kicked_guard_owner',
                None,
            )
            is guard
            for method_name in _KEYBOARD_DEVICE_HOOK_METHODS
        ):
            return False
    return True


def _clipboard_hooks_installed(guard: KickedPopupGuard) -> bool:
    """返回静态剪贴板输入入口是否属于指定守护实例。"""
    try:
        from one_dragon.base.controller.pc_clipboard import PcClipboard

        return all(
            getattr(
                getattr(PcClipboard, method_name, None),
                '_kicked_guard_owner',
                None,
            )
            is guard
            for method_name in _CLIPBOARD_HOOK_METHODS
        )
    except Exception:
        return False


def _is_active_guard(guard: KickedPopupGuard) -> bool:
    """返回该实例是否仍是模块当前生效的守护。"""
    with _active_guard_lock:
        return _active_guard is guard


def get_guard() -> KickedPopupGuard | None:
    """返回当前已安装的守护实例。"""
    with _active_guard_lock:
        return _active_guard


def is_hook_installed() -> bool:
    """返回 Operation 与控制器必需钩子是否均已安装。"""
    try:
        from one_dragon.base.operation.operation import Operation

        guard = get_guard()
        if guard is None:
            return False
        controller = getattr(guard.ctx, 'controller', None)
        if controller is None:
            return False
        return (
            _operation_hooks_installed(Operation, guard)
            and _controller_hooks_installed(controller, guard)
            and _clipboard_hooks_installed(guard)
        )
    except Exception:
        return False
