"""游戏设置调整插件的设置悬浮卡片。"""
from one_dragon_qt.utils.config_utils import get_prop_adapter
from one_dragon_qt.widgets.app_setting.app_setting_flyout import AppSettingFlyout
from one_dragon_qt.widgets.setting_card.switch_setting_card import SwitchSettingCard

from . import game_settings_apply_const


class GameSettingsSettingFlyout(AppSettingFlyout):
    """游戏设置调整设置。"""

    def _setup_ui(self, layout) -> None:
        self.enabled = SwitchSettingCard(
            icon='', title='启用游戏设置调整',
            content='关闭后不改动任何游戏设置。请将"游戏设置调整"排在应用列表最前、"游戏设置还原"排在最后',
            margins=self.card_margins,
        )
        layout.addWidget(self.enabled)

        self.frame_rate_60 = SwitchSettingCard(
            icon='', title='帧率 60（关闭则 30）',
            content='一条龙运行期间锁定的帧率，禁止无限帧率',
            margins=self.card_margins,
        )
        layout.addWidget(self.frame_rate_60)

        self.low_quality = SwitchSettingCard(
            icon='', title='应用最低画质',
            content='关闭后仅写入运行要求项（镜头自动跟随/伤害跳字/字体/帧率），画质保持用户原状',
            margins=self.card_margins,
        )
        layout.addWidget(self.low_quality)

    def init_config(self) -> None:
        config = self.ctx.run_context.get_config(
            app_id=game_settings_apply_const.APP_ID,
            instance_idx=self.ctx.current_instance_idx,
            group_id=self.group_id,
        )
        self.enabled.init_with_adapter(get_prop_adapter(config, 'enabled'))
        self.frame_rate_60.init_with_adapter(get_prop_adapter(config, 'frame_rate_60'))
        self.low_quality.init_with_adapter(get_prop_adapter(config, 'low_quality'))
