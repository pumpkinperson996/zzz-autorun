"""游戏设置插件的用户偏好配置（apply 应用持有）。"""
from one_dragon.base.operation.application.application_config import ApplicationConfig

from . import setting_ids
from .shared_const import APPLY_APP_ID


class GameSettingsConfig(ApplicationConfig):
    """总开关、帧率、低画质子开关。"""

    def __init__(self, instance_idx: int, group_id: str):
        ApplicationConfig.__init__(
            self,
            app_id=APPLY_APP_ID,
            instance_idx=instance_idx,
            group_id=group_id,
        )

    @property
    def enabled(self) -> bool:
        """插件总开关。关闭时 apply 不做任何写入。"""
        return self.get('enabled', True)

    @enabled.setter
    def enabled(self, value: bool) -> None:
        self.update('enabled', value)

    @property
    def frame_rate_60(self) -> bool:
        """帧率目标：True=60，False=30。"""
        return self.get('frame_rate_60', True)

    @frame_rate_60.setter
    def frame_rate_60(self, value: bool) -> None:
        self.update('frame_rate_60', value)

    @property
    def low_quality(self) -> bool:
        """是否同时应用最低画质。关闭时只写运行要求四项。"""
        return self.get('low_quality', True)

    @low_quality.setter
    def low_quality(self, value: bool) -> None:
        self.update('low_quality', value)

    def build_targets(self) -> dict[int, int]:
        """按当前偏好组装要写入的目标值。"""
        frame_rate_value = (
            setting_ids.FRAME_RATE_60 if self.frame_rate_60 else setting_ids.FRAME_RATE_30
        )
        return setting_ids.build_targets(frame_rate_value, self.low_quality)
