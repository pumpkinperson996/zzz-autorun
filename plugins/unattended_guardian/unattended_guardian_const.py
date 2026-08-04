APP_ID = 'unattended_guardian'
APP_NAME = '无人值守安全守护'
DEFAULT_GROUP = True
NEED_NOTIFY = False

PLUGIN_AUTHOR = 'pumpkinperson'
PLUGIN_HOMEPAGE = 'https://github.com/pumpkinperson996/zzz-autorun'
PLUGIN_VERSION = '0.4.0'
PLUGIN_DESCRIPTION = '检测顶号弹窗并熔断运行中未授权重登录，通知后停止一条龙并写入恢复冷却标记'

# 1080p 基准下的居中弹窗区域。
POPUP_CROP_RECT: tuple[int, int, int, int] = (360, 240, 1560, 840)

# 顶号与登录异常弹窗关键词。服务器超时也按用户要求进入同一冷却处理。
DEFAULT_KICKED_KEYWORDS: list[str] = [
    '其他地方登录',
    '账号在其他地方',
    '您的账号在其他',
    '被迫下线',
    '服务器连接超时',
    '是否继续尝试连接',
]

KICKED_CONFIRM_HITS: int = 1
KICKED_TRIGGER_COOLDOWN_SECONDS: int = 60
KICKED_MARKER_FILE: str = 'unattended_kicked_until.txt'

LOGIN_SCREEN_NAME: str = '打开游戏'
LOGIN_SCREEN_TEMPLATE_AREAS: tuple[str, ...] = (
    '资源检测',
    '设置',
    '游戏公告',
    '切换账号',
)
LOGIN_SCREEN_REQUIRED_TEMPLATE_HITS: int = 2
AUTHORIZED_LOGIN_MODULE_PREFIX: str = 'zzz_od.operation.enter_game'
TRUSTED_ACCOUNT_SWITCH_MODULE_PREFIX: str = (
    'zzz_od.operation.enter_game.switch_account'
)
LOGIN_BLOCKED_STATUS: str = '顶号保护已阻断登录'
PASSIVE_OPERATION_MODULE_PREFIXES: tuple[str, ...] = (
    'unattended_guardian.',
    'plugins.unattended_guardian.',
)
INPUT_FRAME_MAX_AGE_SECONDS: float = 0.05
SDK_LOG_POLL_SECONDS: float = 0.1
SDK_RELOGIN_LOG_MARKERS: tuple[str, ...] = (
    'func name is:web_set_joypad_enable_external',
    'func name is:login_account_plat',
)
