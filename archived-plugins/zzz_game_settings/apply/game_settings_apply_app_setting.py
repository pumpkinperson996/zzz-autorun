from one_dragon_qt.services.app_setting.app_setting_provider import (
    AppSettingProvider,
    SettingType,
)

from .game_settings_apply_const import APP_ID


class GameSettingsApplySetting(AppSettingProvider):
    app_id = APP_ID
    setting_type = SettingType.FLYOUT

    @staticmethod
    def get_setting_cls() -> type:
        from .game_settings_setting_flyout import GameSettingsSettingFlyout
        return GameSettingsSettingFlyout
