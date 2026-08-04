"""定位并调用一条龙 GUI 首页的「启动一条龙」按钮。

优先使用 Windows UI Automation；Qt 未暴露按钮时，使用 Windows Media OCR
识别当前 Qt 客户区。脚本是单次命令，不承担运行期监控或顶号检测。
"""
from __future__ import annotations

import argparse
import asyncio
import contextlib
import re
import subprocess
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

TARGET_TEXT: str = '启动一条龙'
QT_CLASS_PATTERN: re.Pattern[str] = re.compile(r'^Qt\d+QWindowIcon$')
TREE_SCOPE_DESCENDANTS: int = 4
RETRY_EXIT_CODE: int = 2
ERROR_EXIT_CODE: int = 3


@dataclass(frozen=True)
class OcrCandidate:
    """OCR 行及其客户区坐标。"""

    text: str
    x: float
    y: float
    width: float
    height: float

    @property
    def center_x(self) -> float:
        return self.x + self.width / 2

    @property
    def center_y(self) -> float:
        return self.y + self.height / 2


def normalize_text(text: str) -> str:
    """去除 OCR 常见空白与装饰符号，保留中文语义。"""
    return re.sub(r'[\s·•🚀]+', '', text or '')


def parse_window_handle(value: str) -> int:
    """同时解析 AHK 的十六进制句柄与命令行常见的十进制句柄。"""
    return int(value, 0)


def select_start_candidate(
        candidates: list[OcrCandidate],
        client_width: int,
        client_height: int,
) -> OcrCandidate | None:
    """筛选客户区右下方完整命中目标文字的安全候选。"""
    if client_width <= 0 or client_height <= 0:
        return None

    safe: list[OcrCandidate] = []
    for candidate in candidates:
        if normalize_text(candidate.text) != TARGET_TEXT:
            continue
        if candidate.width <= 0 or candidate.height <= 0:
            continue
        if candidate.x < 0 or candidate.y < 0:
            continue
        if candidate.x + candidate.width > client_width:
            continue
        if candidate.y + candidate.height > client_height:
            continue
        if candidate.center_x < client_width * 0.45:
            continue
        if candidate.center_y < client_height * 0.45:
            continue
        safe.append(candidate)

    if not safe:
        return None
    return max(safe, key=lambda item: (item.center_y, item.center_x))


def is_point_in_rect(x: int, y: int, rect: tuple[int, int, int, int]) -> bool:
    """判断点是否位于左闭右开矩形内。"""
    left, top, right, bottom = rect
    return left <= x < right and top <= y < bottom


def _set_dpi_awareness() -> None:
    """关闭 DPI 虚拟化，保证截图像素与点击坐标一致。"""
    import ctypes

    try:
        ctypes.windll.user32.SetProcessDpiAwarenessContext(ctypes.c_void_p(-4))
    except Exception:
        with contextlib.suppress(Exception):
            ctypes.windll.user32.SetProcessDPIAware()


def find_qt_window() -> int | None:
    """查找当前可见的一条龙 Qt 主窗口。"""
    import win32gui

    matches: list[int] = []

    def callback(hwnd: int, _: Any) -> None:
        if not win32gui.IsWindowVisible(hwnd):
            return
        class_name = win32gui.GetClassName(hwnd)
        title = win32gui.GetWindowText(hwnd)
        if QT_CLASS_PATTERN.match(class_name) and '一条龙' in title:
            matches.append(hwnd)

    win32gui.EnumWindows(callback, None)
    return matches[0] if matches else None


def get_client_geometry(hwnd: int) -> tuple[int, int, int, int]:
    """返回客户区屏幕原点与尺寸。"""
    import win32gui

    left, top = win32gui.ClientToScreen(hwnd, (0, 0))
    client_left, client_top, client_right, client_bottom = win32gui.GetClientRect(hwnd)
    width = client_right - client_left
    height = client_bottom - client_top
    return left, top, width, height


def get_virtual_screen_rect() -> tuple[int, int, int, int]:
    """返回 Windows 虚拟桌面边界。"""
    import win32api

    left = win32api.GetSystemMetrics(76)  # SM_XVIRTUALSCREEN
    top = win32api.GetSystemMetrics(77)  # SM_YVIRTUALSCREEN
    width = win32api.GetSystemMetrics(78)  # SM_CXVIRTUALSCREEN
    height = win32api.GetSystemMetrics(79)  # SM_CYVIRTUALSCREEN
    return left, top, left + width, top + height


def run_uia(hwnd: int, locate_only: bool) -> tuple[int, str]:
    """调用 PowerShell UIA 适配层。"""
    script = Path(__file__).with_name('click_start_button_uia.ps1')
    command: list[str] = [
        'powershell.exe',
        '-NoProfile',
        '-ExecutionPolicy',
        'Bypass',
        '-File',
        str(script),
        '-Hwnd',
        str(hwnd),
    ]
    if locate_only:
        command.append('-LocateOnly')

    try:
        result = subprocess.run(
            command,
            capture_output=True,
            text=True,
            encoding='utf-8',
            errors='replace',
            timeout=15,
            check=False,
        )
    except Exception as exc:
        return ERROR_EXIT_CODE, f'ERROR:UIA_RUN:{exc}'

    output = (result.stdout or result.stderr or '').strip().splitlines()
    message = output[-1].strip() if output else f'ERROR:UIA_EXIT_{result.returncode}'
    return result.returncode, message


def capture_client(hwnd: int) -> tuple[Any, tuple[int, int, int, int]]:
    """截图 Qt 客户区并返回图像及屏幕几何。"""
    import mss
    from PIL import Image

    left, top, width, height = get_client_geometry(hwnd)
    if width <= 0 or height <= 0:
        raise RuntimeError('Qt 客户区尺寸无效')

    with mss.MSS() as capture:
        shot = capture.grab({
            'left': left,
            'top': top,
            'width': width,
            'height': height,
        })
    image = Image.frombytes('RGB', shot.size, shot.bgra, 'raw', 'BGRX')
    return image, (left, top, width, height)


async def recognize_candidates(image: Any) -> list[OcrCandidate]:
    """使用 Windows Media OCR 返回带位置的文本行。"""
    from PIL import Image
    from winrt.windows.globalization import Language
    from winrt.windows.graphics.imaging import BitmapPixelFormat, SoftwareBitmap
    from winrt.windows.media.ocr import OcrEngine
    from winrt.windows.security.cryptography import CryptographicBuffer

    rgba: Image.Image = image.convert('RGBA')
    red, green, blue, alpha = rgba.split()
    bgra = Image.merge('RGBA', (blue, green, red, alpha))
    buffer = CryptographicBuffer.create_from_byte_array(bgra.tobytes())
    bitmap = SoftwareBitmap.create_copy_from_buffer(
        buffer,
        BitmapPixelFormat.BGRA8,
        image.width,
        image.height,
    )
    try:
        engine = OcrEngine.try_create_from_language(Language('zh-CN'))
        if engine is None:
            engine = OcrEngine.try_create_from_user_profile_languages()
        if engine is None:
            raise RuntimeError('Windows OCR 引擎不可用，请安装简体中文语言包')

        result = await engine.recognize_async(bitmap)
        candidates: list[OcrCandidate] = []
        for line in result.lines:
            words = list(line.words)
            if not words:
                continue
            left = min(float(word.bounding_rect.x) for word in words)
            top = min(float(word.bounding_rect.y) for word in words)
            right = max(
                float(word.bounding_rect.x + word.bounding_rect.width)
                for word in words
            )
            bottom = max(
                float(word.bounding_rect.y + word.bounding_rect.height)
                for word in words
            )
            candidates.append(OcrCandidate(
                text=line.text,
                x=left,
                y=top,
                width=right - left,
                height=bottom - top,
            ))
        return candidates
    finally:
        close = getattr(bitmap, 'close', None)
        if callable(close):
            close()


def click_screen_point(hwnd: int, x: int, y: int) -> None:
    """激活 Qt 窗口并在物理屏幕坐标点击。"""
    import win32api
    import win32con
    import win32gui

    win32gui.ShowWindow(hwnd, win32con.SW_RESTORE)
    with contextlib.suppress(Exception):
        win32gui.SetForegroundWindow(hwnd)
    win32api.SetCursorPos((x, y))
    time.sleep(0.08)
    win32api.mouse_event(win32con.MOUSEEVENTF_LEFTDOWN, 0, 0, 0, 0)
    win32api.mouse_event(win32con.MOUSEEVENTF_LEFTUP, 0, 0, 0, 0)


def run_ocr(hwnd: int, locate_only: bool) -> tuple[int, str]:
    """OCR 定位并按需点击启动按钮。"""
    try:
        image, geometry = capture_client(hwnd)
        left, top, width, height = geometry
        candidates = asyncio.run(recognize_candidates(image))
        candidate = select_start_candidate(candidates, width, height)
        if candidate is None:
            preview = '|'.join(normalize_text(item.text) for item in candidates[:8])
            return RETRY_EXIT_CODE, f'RETRY:OCR_BUTTON_NOT_FOUND:{preview[:160]}'

        screen_x = int(round(left + candidate.center_x))
        screen_y = int(round(top + candidate.center_y))
        client_rect = (left, top, left + width, top + height)
        if not is_point_in_rect(screen_x, screen_y, client_rect):
            return ERROR_EXIT_CODE, 'ERROR:OCR_POINT_OUTSIDE_CLIENT'
        if not is_point_in_rect(screen_x, screen_y, get_virtual_screen_rect()):
            return ERROR_EXIT_CODE, 'ERROR:OCR_POINT_OUTSIDE_SCREEN'

        if not locate_only:
            click_screen_point(hwnd, screen_x, screen_y)
        return 0, f'OK:OCR:x={screen_x},y={screen_y}'
    except Exception as exc:
        return ERROR_EXIT_CODE, f'ERROR:OCR:{exc}'


def write_result(message: str, result_file: Path | None) -> None:
    """同时向标准输出与可选结果文件写入单行结果。"""
    safe_message = message.replace('\r', ' ').replace('\n', ' ')
    print(safe_message, flush=True)
    if result_file is not None:
        result_file.write_text(safe_message, encoding='utf-8')


def parse_args() -> argparse.Namespace:
    """解析命令行参数。"""
    parser = argparse.ArgumentParser(description='定位并调用一条龙 GUI 启动按钮')
    parser.add_argument(
        '--hwnd',
        type=parse_window_handle,
        help='Qt 主窗口句柄；支持十进制和 AHK 的 0x 十六进制格式',
    )
    parser.add_argument('--result-file', type=Path, help='供 AHK 读取的 UTF-8 结果文件')
    parser.add_argument('--locate-only', action='store_true', help='只定位，不调用或点击')
    parser.add_argument('--skip-uia', action='store_true', help='跳过 UIA，直接验证 OCR 兜底')
    return parser.parse_args()


def main() -> int:
    """运行 UIA 优先、OCR 兜底的单次定位。"""
    _set_dpi_awareness()
    args = parse_args()
    hwnd = args.hwnd or find_qt_window()
    if hwnd is None:
        write_result('RETRY:QT_WINDOW_NOT_FOUND', args.result_file)
        return RETRY_EXIT_CODE

    uia_message = ''
    if not args.skip_uia:
        uia_code, uia_message = run_uia(hwnd, args.locate_only)
        if uia_code == 0:
            write_result(uia_message, args.result_file)
            return 0

    ocr_code, ocr_message = run_ocr(hwnd, args.locate_only)
    if ocr_code != 0 and uia_message:
        ocr_message = f'{ocr_message};{uia_message}'
    write_result(ocr_message, args.result_file)
    return ocr_code


if __name__ == '__main__':
    sys.exit(main())
