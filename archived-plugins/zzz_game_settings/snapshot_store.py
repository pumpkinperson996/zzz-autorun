"""跨 apply/restore 共享的快照状态存储。

独立于框架的 ApplicationConfig，因为快照是设备级可变状态、需要被两个应用共享读写。
持久化到 config/{idx}/{group}/game_settings_state.yml，实现崩溃恢复语义所需的
snapshot_pending 标记。
"""
import os

from one_dragon.base.config.yaml_operator import YamlOperator
from one_dragon.utils import os_utils

from .shared_const import APPLY_APP_ID


class SnapshotStore(YamlOperator):
    """保存用户设置快照块与待还原标记。"""

    def __init__(self, instance_idx: int, group_id: str, file_path: str | None = None):
        if file_path is None:
            file_path = os.path.join(
                os_utils.get_path_under_work_dir('config', f'{instance_idx:02d}', group_id),
                f'{APPLY_APP_ID}_state.yml',
            )
        YamlOperator.__init__(self, file_path=file_path)

    @property
    def snapshot_pending(self) -> bool:
        """是否存在尚未还原的用户设置快照。"""
        return self.get('snapshot_pending', False)

    @property
    def snapshot_block(self) -> str:
        """用户设置的 SystemSettingDataMap 快照文本块。"""
        return self.get('snapshot_block', '')

    @property
    def snapshot_time(self) -> str:
        return self.get('snapshot_time', '')

    def save_snapshot(self, block: str, snapshot_time: str) -> None:
        """记录快照并置位待还原标记（不覆盖已有的 pending 快照由调用方判断）。"""
        self.data['snapshot_block'] = block
        self.data['snapshot_time'] = snapshot_time
        self.data['snapshot_pending'] = True
        self.save()

    def clear_pending(self) -> None:
        """还原成功后清除待还原标记。"""
        self.update('snapshot_pending', False)
