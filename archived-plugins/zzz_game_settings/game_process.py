"""游戏进程检测工具。

不依赖 psutil（仅 dev 分组），用 Windows 自带的 tasklist 查询进程名。
"""
import subprocess
import time
from pathlib import Path


def process_name_from_game_path(game_path: str) -> str:
    """从游戏 exe 路径取进程名，如 ...\\ZenlessZoneZero.exe -> ZenlessZoneZero.exe。"""
    return Path(game_path).name


def is_game_running(process_name: str) -> bool:
    """查询指定进程名是否存在。任何异常都保守返回 True（宁可不写盘也不误判为已退出）。"""
    if not process_name:
        return False
    try:
        result = subprocess.run(
            ['tasklist', '/FI', f'IMAGENAME eq {process_name}', '/NH'],
            capture_output=True,
            text=True,
            creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0),
            timeout=15,
        )
    except (OSError, subprocess.SubprocessError):
        return True
    return process_name.lower() in result.stdout.lower()


def wait_process_exit(process_name: str, timeout_seconds: float = 30.0,
                      poll_interval: float = 1.0) -> bool:
    """轮询等待进程退出，返回是否在超时前退出。"""
    deadline = time.time() + timeout_seconds
    while time.time() < deadline:
        if not is_game_running(process_name):
            return True
        time.sleep(poll_interval)
    return not is_game_running(process_name)
