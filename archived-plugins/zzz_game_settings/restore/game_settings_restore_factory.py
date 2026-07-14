from typing import TYPE_CHECKING

from one_dragon.base.operation.application.application_factory import ApplicationFactory
from one_dragon.base.operation.application_base import Application
from one_dragon.base.operation.application_run_record import AppRunRecord

from . import game_settings_restore_const
from .game_settings_restore_app import GameSettingsRestoreApp

if TYPE_CHECKING:
    from zzz_od.context.zzz_context import ZContext


class GameSettingsRestoreFactory(ApplicationFactory):

    def __init__(self, ctx: 'ZContext'):
        ApplicationFactory.__init__(self, game_settings_restore_const)
        self.ctx: ZContext = ctx

    def create_application(self, instance_idx: int, group_id: str) -> Application:
        return GameSettingsRestoreApp(self.ctx)

    def create_run_record(self, instance_idx: int) -> AppRunRecord:
        return AppRunRecord(
            app_id=game_settings_restore_const.APP_ID,
            instance_idx=instance_idx,
            game_refresh_hour_offset=self.ctx.game_account_config.game_refresh_hour_offset,
        )
