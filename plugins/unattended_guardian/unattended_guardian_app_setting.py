from one_dragon_qt.services.app_setting.app_setting_provider import (
    AppSettingProvider,
    SettingType,
)

from .unattended_guardian_const import APP_ID


class UnattendedGuardianAppSetting(AppSettingProvider):
    app_id = APP_ID
    setting_type = SettingType.FLYOUT

    @staticmethod
    def get_setting_cls() -> type:
        from .guardian_setting_flyout import GuardianSettingFlyout
        return GuardianSettingFlyout
