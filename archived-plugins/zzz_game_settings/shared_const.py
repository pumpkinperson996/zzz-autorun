"""两个应用共享的 APP_ID 常量。

配置文件名与状态文件名依赖 apply 应用的 APP_ID；集中在此避免顶层共享模块反向
依赖 apply 子包。const 子模块中的 APP_ID 字面量需与此保持一致。
"""

APPLY_APP_ID: str = 'game_settings_apply'
RESTORE_APP_ID: str = 'game_settings_restore'
