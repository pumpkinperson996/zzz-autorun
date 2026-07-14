"""GENERAL_DATA.bin 的定位与安全写入协议。

把 codec（编解码）、settings_block（文本外科手术）、备份/复核 组装为对外的
读写接口。所有写盘都走 write_targets / restore_block，内部强制往返自检、备份、
写后复核回滚。进程检测由调用方（Application）在写盘前完成。
"""
import contextlib
import time
from pathlib import Path

from one_dragon.utils.log_utils import log

from . import settings_block
from .general_data_codec import GeneralData, GeneralDataFormatError, verify_roundtrip

_LOCAL_STORAGE_SUFFIX = (
    'ZenlessZoneZero_Data', 'Persistent', 'LocalStorage', 'GENERAL_DATA.bin',
)
_BACKUP_KEEP = 5


def resolve_general_data_path(game_path: str) -> Path:
    """由游戏 exe 路径推出 GENERAL_DATA.bin 路径。"""
    return Path(game_path).parent.joinpath(*_LOCAL_STORAGE_SUFFIX)


class GameSettingsFile:
    """对单个 GENERAL_DATA.bin 的安全读写。"""

    def __init__(self, path: Path):
        self.path: Path = path

    def exists(self) -> bool:
        return self.path.is_file()

    def _load_verified(self) -> GeneralData:
        """读取并做格式+往返自检，任一失败抛 GeneralDataFormatError。"""
        raw = self.path.read_bytes()
        if not verify_roundtrip(raw):
            raise GeneralDataFormatError('往返自检失败，游戏版本可能已更新')
        return GeneralData.parse(raw)

    def snapshot_map_block(self) -> str:
        """截取当前 SystemSettingDataMap 文本块作为快照。"""
        data = self._load_verified()
        return settings_block.extract_map_block(data.text)

    def _backup(self) -> Path:
        stamp = time.strftime('%Y%m%d_%H%M%S')
        bak = self.path.with_name(f'{self.path.name}.bak_{stamp}')
        bak.write_bytes(self.path.read_bytes())
        self._prune_backups()
        return bak

    def _prune_backups(self) -> None:
        backups = sorted(
            self.path.parent.glob(f'{self.path.name}.bak_*'),
            key=lambda p: p.name,
        )
        for old in backups[:-_BACKUP_KEEP]:
            with contextlib.suppress(OSError):
                old.unlink()

    def _write_and_verify(self, new_text: str, verify) -> None:
        """写入 new_text，写后重解码并调用 verify 复核，失败则用备份回滚。

        verify: Callable[[str], bool]，接收写入后重解码的文本，返回是否符合预期。
        """
        data = self._load_verified()
        bak = self._backup()
        self.path.write_bytes(data.encode(new_text))
        try:
            reread = GeneralData.parse(self.path.read_bytes())
            if not verify(reread.text):
                raise GeneralDataFormatError('写后复核不通过')
        except GeneralDataFormatError:
            self.path.write_bytes(bak.read_bytes())
            log.error('游戏设置写入复核失败，已用备份回滚: %s', bak.name)
            raise

    def write_targets(self, targets: dict[int, int]) -> None:
        """把一组 {设置ID: 目标值} 写入文件。"""
        data = self._load_verified()
        text = data.text
        for setting_id, value in targets.items():
            text = settings_block.set_setting_value(text, setting_id, value)

        def _verify(reread_text: str) -> bool:
            return all(
                settings_block.get_setting_value(reread_text, sid) == val
                for sid, val in targets.items()
            )

        self._write_and_verify(text, _verify)
        log.info('已写入 %d 项游戏设置', len(targets))

    def restore_block(self, snapshot_block: str) -> None:
        """用快照的 SystemSettingDataMap 块整体替换当前块（还原用户设置）。"""
        data = self._load_verified()
        new_text = settings_block.replace_map_block(data.text, snapshot_block)

        def _verify(reread_text: str) -> bool:
            return settings_block.extract_map_block(reread_text) == snapshot_block

        self._write_and_verify(new_text, _verify)
        log.info('已还原游戏设置至快照')
