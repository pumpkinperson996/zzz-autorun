"""游戏设置调整应用：一条龙启动后、正式任务前，把游戏设置改为低画质+运行要求。

排在一条龙应用列表最前。一条龙会先「打开并进入游戏」再跑应用组，因此本应用运行时
游戏已在运行、且处于大世界。游戏只在启动时读取设置文件，改磁盘不影响运行中的游戏，
所以流程为：关闭游戏 → 写入目标设置 → 重新打开游戏进大世界（此时游戏以低画质加载）。
重开是为了让低画质本次生效，同时保持应用组后续节点所需的「游戏窗口存在」。
任何情况下都不把游戏留在关闭状态，否则应用组的截图节点会崩溃。
"""
import time
from typing import TYPE_CHECKING

from one_dragon.base.operation.application import application_const
from one_dragon.base.operation.operation_edge import node_from
from one_dragon.base.operation.operation_node import operation_node
from one_dragon.base.operation.operation_round_result import OperationRoundResult
from one_dragon.utils.log_utils import log
from zzz_game_settings import game_settings_service
from zzz_game_settings.game_settings_config import GameSettingsConfig
from zzz_game_settings.general_data_codec import GeneralDataFormatError
from zzz_game_settings.settings_file import GameSettingsFile
from zzz_game_settings.snapshot_store import SnapshotStore
from zzz_od.application.zzz_application import ZApplication
from zzz_od.operation.enter_game.open_and_enter_game import OpenAndEnterGame

from . import game_settings_apply_const

if TYPE_CHECKING:
    from zzz_od.context.zzz_context import ZContext


class GameSettingsApplyApp(ZApplication):

    def __init__(self, ctx: 'ZContext'):
        ZApplication.__init__(
            self,
            ctx=ctx,
            app_id=game_settings_apply_const.APP_ID,
            op_name=game_settings_apply_const.APP_NAME,
            need_check_game_win=False,
        )
        config = self.ctx.run_context.get_config(
            app_id=game_settings_apply_const.APP_ID,
            instance_idx=self.ctx.current_instance_idx,
            group_id=application_const.DEFAULT_GROUP_ID,
        )
        self.config: GameSettingsConfig = config
        self.store: SnapshotStore = SnapshotStore(
            instance_idx=self.ctx.current_instance_idx,
            group_id=application_const.DEFAULT_GROUP_ID,
        )
        self._file: GameSettingsFile | None = None

    @operation_node(name='检查启用', is_start_node=True, screenshot_before_round=False)
    def check_enabled(self) -> OperationRoundResult:
        if not self.config.enabled:
            return self.round_success('插件未启用')
        self._file = game_settings_service.get_settings_file(self.ctx)
        if self._file is None:
            return self.round_fail('未找到游戏设置文件（检查游戏路径）')
        return self.round_success()

    @node_from(from_name='检查启用')
    @operation_node(name='关闭游戏进程', screenshot_before_round=False)
    def close_game(self) -> OperationRoundResult:
        # _file 为 None 仅出现在插件未启用时（启用但文件缺失会在上一节点 round_fail）
        if self._file is None:
            return self.round_success()
        if not game_settings_service.ensure_game_closed(self.ctx):
            # 游戏仍在运行，未做任何改动，游戏窗口仍在，交回应用组即可
            return self.round_fail('游戏未能关闭，跳过设置调整')
        return self.round_success()

    @node_from(from_name='关闭游戏进程')
    @operation_node(name='写入目标设置', screenshot_before_round=False)
    def apply_settings(self) -> OperationRoundResult:
        if self._file is None:  # 未启用
            return self.round_success()
        try:
            if self.store.snapshot_pending:
                # 上一轮未正常还原，保留用户原始快照，不重新覆盖
                log.info('检测到未还原的快照，跳过重新快照')
            else:
                block = self._file.snapshot_map_block()
                self.store.save_snapshot(block, time.strftime('%Y-%m-%d %H:%M:%S'))
                log.info('已快照当前游戏设置')

            self._file.write_targets(self.config.build_targets())
            return self.round_success('已写入目标设置')
        except GeneralDataFormatError as e:
            # 写入失败不改动文件；返回成功以继续重开游戏，避免把游戏留在关闭状态
            log.error('游戏设置文件格式异常，本轮跳过写入: %s', e)
            return self.round_success('格式异常已跳过')

    @node_from(from_name='写入目标设置')
    @operation_node(name='重新打开游戏', screenshot_before_round=False)
    def reopen_game(self) -> OperationRoundResult:
        if self._file is None:  # 未启用，未关闭游戏，无需重开
            return self.round_success()
        op = OpenAndEnterGame(self.ctx)
        return self.round_by_op_result(op.execute())
