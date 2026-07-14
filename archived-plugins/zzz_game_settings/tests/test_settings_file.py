"""安全写入协议测试（write_targets / restore_block / 备份 / 复核）。"""

from plugins.zzz_game_settings import settings_block
from plugins.zzz_game_settings.general_data_codec import GeneralData
from plugins.zzz_game_settings.settings_file import GameSettingsFile
from plugins.zzz_game_settings.tests.sample_builder import build_sample_bytes


def _make_file(tmp_path) -> GameSettingsFile:
    p = tmp_path / 'GENERAL_DATA.bin'
    p.write_bytes(build_sample_bytes())
    return GameSettingsFile(p)


def _current_value(file: GameSettingsFile, setting_id: int) -> int | None:
    data = GeneralData.parse(file.path.read_bytes())
    return settings_block.get_setting_value(data.text, setting_id)


def test_write_targets_changes_values(tmp_path) -> None:
    file = _make_file(tmp_path)
    file.write_targets({87: 0, 110: 0, 74: 0})
    assert _current_value(file, 87) == 0
    assert _current_value(file, 110) == 0
    assert _current_value(file, 74) == 0  # 新增条目


def test_write_creates_backup(tmp_path) -> None:
    file = _make_file(tmp_path)
    file.write_targets({87: 0})
    backups = list(tmp_path.glob('GENERAL_DATA.bin.bak_*'))
    assert len(backups) == 1


def test_snapshot_then_restore(tmp_path) -> None:
    file = _make_file(tmp_path)
    snapshot = file.snapshot_map_block()

    file.write_targets({87: 0, 110: 0, 74: 0})
    assert _current_value(file, 87) == 0

    file.restore_block(snapshot)
    assert _current_value(file, 87) == 1  # 回到原值
    assert _current_value(file, 110) == 1
    assert _current_value(file, 74) is None  # 新增条目消失


def test_restore_keeps_outside_fields(tmp_path) -> None:
    file = _make_file(tmp_path)
    snapshot = file.snapshot_map_block()
    file.write_targets({87: 0})
    file.restore_block(snapshot)
    data = GeneralData.parse(file.path.read_bytes())
    assert 'HDRSettingRecordState' in data.text
