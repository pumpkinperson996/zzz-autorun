"""游戏设置还原应用：一条龙结束前把设置还原为用户原始配置。

排在一条龙应用列表最后。流程：关闭游戏 → 写回用户快照 → 重新打开游戏进大世界。
重开有两个作用：
1. 保持应用组收尾节点所需的「游戏窗口存在」，否则截图会崩溃；
2. 让游戏以「用户原始设置」加载进内存，这样一条龙最终的关闭游戏在退出回写时
   写入的仍是用户设置，磁盘保持用户配置。
若不重开，游戏退出时会用内存中的低画质回写，覆盖我们还原的用户设置。
"""
from typing import TYPE_CHECKING

from one_dragon.base.operation.application import application_const
from one_dragon.base.operation.operation_edge import node_from
from one_dragon.base.operation.operation_node import operation_node
from one_dragon.base.operation.operation_round_result import OperationRoundResult
from one_dragon.utils.log_utils import log
from zzz_game_settings import game_settings_service
from zzz_game_settings.general_data_codec import GeneralDataFormatError
from zzz_game_settings.settings_file import GameSettingsFile
from zzz_game_settings.snapshot_store import SnapshotStore
from zzz_od.application.zzz_application import ZApplication
from zzz_od.operation.enter_game.open_and_enter_game import OpenAndEnterGame

from . import game_settings_restore_const

if TYPE_CHECKING:
    from zzz_od.context.zzz_context import ZContext


class GameSettingsRestoreApp(ZApplication):

    def __init__(self, ctx: 'ZContext'):
        ZApplication.__init__(
            self,
            ctx=ctx,
            app_id=game_settings_restore_const.APP_ID,
            op_name=game_settings_restore_const.APP_NAME,
            need_check_game_win=False,
        )
        self.store: SnapshotStore = SnapshotStore(
            instance_idx=self.ctx.current_instance_idx,
            group_id=application_const.DEFAULT_GROUP_ID,
        )
        self._file: GameSettingsFile | None = None

    @operation_node(name='检查待还原快照', is_start_node=True, screenshot_before_round=False)
    def check_snapshot(self) -> OperationRoundResult:
        if not self.store.snapshot_pending or not self.store.snapshot_block:
            return self.round_success('无待还原快照')
        self._file = game_settings_service.get_settings_file(self.ctx)
        if self._file is None:
            return self.round_fail('未找到游戏设置文件（检查游戏路径）')
        return self.round_success()

    @node_from(from_name='检查待还原快照')
    @operation_node(name='关闭游戏进程', screenshot_before_round=False)
    def close_game(self) -> OperationRoundResult:
        if self._file is None:  # 无快照，跳过
            return self.round_success()
        if not game_settings_service.ensure_game_closed(self.ctx):
            return self.round_fail('游戏未能关闭，保留待还原标记下次补还原')
        return self.round_success()

    @node_from(from_name='关闭游戏进程')
    @operation_node(name='还原用户设置', screenshot_before_round=False)
    def restore(self) -> OperationRoundResult:
        if self._file is None:  # 无快照
            return self.round_success()
        try:
            self._file.restore_block(self.store.snapshot_block)
            self.store.clear_pending()
            return self.round_success('已还原用户设置')
        except GeneralDataFormatError as e:
            # 还原失败保留 pending 供下次补还原；仍继续重开游戏避免留在关闭状态
            log.error('还原失败，保留待还原标记以便下次补还原: %s', e)
            return self.round_success('还原失败已跳过')

    @node_from(from_name='还原用户设置')
    @operation_node(name='重新打开游戏', screenshot_before_round=False)
    def reopen_game(self) -> OperationRoundResult:
        if self._file is None:  # 无快照，未关闭游戏，无需重开
            return self.round_success()
        op = OpenAndEnterGame(self.ctx)
        return self.round_by_op_result(op.execute())
