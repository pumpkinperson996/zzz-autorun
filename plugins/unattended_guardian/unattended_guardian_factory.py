from typing import TYPE_CHECKING

from one_dragon.base.operation.application.application_config import ApplicationConfig
from one_dragon.base.operation.application.application_factory import ApplicationFactory
from one_dragon.base.operation.application_base import Application
from one_dragon.base.operation.application_run_record import AppRunRecord

from . import unattended_guardian_const
from .screenshot_hook import ensure_hook_installed, install_hook
from .unattended_guardian_app import UnattendedGuardianApp

if TYPE_CHECKING:
    from zzz_od.context.zzz_context import ZContext


class UnattendedGuardianFactory(ApplicationFactory):

    def __init__(self, ctx: 'ZContext') -> None:
        ApplicationFactory.__init__(self, unattended_guardian_const)
        self.ctx: ZContext = ctx
        # 工厂在插件扫描时实例化，因此检测不依赖守护循环或计划任务。
        install_hook(ctx)

    def create_application(self, instance_idx: int, group_id: str) -> Application:
        # 工厂扫描早于控制器初始化；创建应用时再绑定一次真实控制器。
        ensure_hook_installed(self.ctx)
        return UnattendedGuardianApp(self.ctx)

    def create_config(self, instance_idx: int, group_id: str) -> ApplicationConfig:
        return ApplicationConfig(
            app_id=unattended_guardian_const.APP_ID,
            instance_idx=instance_idx,
            group_id=group_id,
        )

    def create_run_record(self, instance_idx: int) -> AppRunRecord:
        return AppRunRecord(
            app_id=unattended_guardian_const.APP_ID,
            instance_idx=instance_idx,
            game_refresh_hour_offset=self.ctx.game_account_config.game_refresh_hour_offset,
        )
