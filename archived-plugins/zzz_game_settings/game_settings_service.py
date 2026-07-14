"""apply 与 restore 共用的辅助逻辑：定位文件、关闭并等待游戏退出。"""
from typing import TYPE_CHECKING

from one_dragon.utils.log_utils import log

from . import game_process
from .settings_file import GameSettingsFile, resolve_general_data_path

if TYPE_CHECKING:
    from zzz_od.context.zzz_context import ZContext


def get_settings_file(ctx: 'ZContext') -> GameSettingsFile | None:
    """按当前实例的游戏路径构造 GameSettingsFile；未配置或文件缺失返回 None。"""
    game_path = ctx.game_account_config.game_path
    if not game_path:
        return None
    file = GameSettingsFile(resolve_general_data_path(game_path))
    return file if file.exists() else None


def game_process_name(ctx: 'ZContext') -> str:
    return game_process.process_name_from_game_path(ctx.game_account_config.game_path)


def ensure_game_closed(ctx: 'ZContext', timeout_seconds: float = 30.0) -> bool:
    """若游戏在运行则关闭并等待进程退出。返回最终是否已退出。

    游戏退出时会整体回写设置文件，因此写盘必须在进程完全退出之后进行。
    """
    name = game_process_name(ctx)
    if not game_process.is_game_running(name):
        return True

    log.info('检测到游戏运行中，正在关闭...')
    try:
        ctx.controller.close_game()
    except Exception:
        log.error('关闭游戏调用异常', exc_info=True)

    exited = game_process.wait_process_exit(name, timeout_seconds=timeout_seconds)
    if not exited:
        log.error('等待游戏退出超时')
    return exited
