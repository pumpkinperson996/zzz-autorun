from one_dragon.base.operation.operation_node import operation_node
from one_dragon.base.operation.operation_round_result import OperationRoundResult
from zzz_od.application.zzz_application import ZApplication
from zzz_od.context.zzz_context import ZContext

from . import unattended_guardian_const
from .screenshot_hook import ensure_hook_installed, get_guard, is_hook_installed
from .unattended_guardian_config import get_config


class UnattendedGuardianApp(ZApplication):
    """展示顶号检测状态；检测钩子在插件注册时已经安装。"""

    def __init__(self, ctx: ZContext) -> None:
        ZApplication.__init__(
            self,
            ctx=ctx,
            app_id=unattended_guardian_const.APP_ID,
            op_name=unattended_guardian_const.APP_NAME,
            need_check_game_win=False,
        )

    @operation_node(name='检查顶号检测', is_start_node=True, screenshot_before_round=False)
    def check_detector(self) -> OperationRoundResult:
        if not ensure_hook_installed(self.ctx):
            return self.round_fail('顶号检测未能绑定真实控制器，请查看日志')
        if not is_hook_installed():
            return self.round_fail('顶号检测钩子未安装成功，请查看日志')
        if not get_config().detect_enabled:
            return self.round_success('顶号检测当前已关闭')
        guard = get_guard()
        if guard is None:
            return self.round_fail('顶号检测守护实例不存在，请查看日志')
        return self.round_success('顶号检测与重登录熔断已启用')
