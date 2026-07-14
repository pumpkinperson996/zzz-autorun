"""SystemSettingDataMap 文本外科手术测试。"""
from plugins.zzz_game_settings import settings_block
from plugins.zzz_game_settings.tests.sample_builder import SAMPLE_TEXT


def test_get_existing_value() -> None:
    assert settings_block.get_setting_value(SAMPLE_TEXT, 12155) == 2
    assert settings_block.get_setting_value(SAMPLE_TEXT, 87) == 1


def test_get_missing_value() -> None:
    assert settings_block.get_setting_value(SAMPLE_TEXT, 9999) is None


def test_set_existing_value() -> None:
    out = settings_block.set_setting_value(SAMPLE_TEXT, 12155, 0)
    assert settings_block.get_setting_value(out, 12155) == 0
    # 其余条目不受影响
    assert settings_block.get_setting_value(out, 87) == 1
    assert settings_block.get_setting_value(out, 110) == 1


def test_set_only_changes_target_bytes() -> None:
    out = settings_block.set_setting_value(SAMPLE_TEXT, 87, 0)
    # 仅一个字符不同（1 -> 0）
    assert len(out) == len(SAMPLE_TEXT)
    diff = [i for i in range(len(out)) if out[i] != SAMPLE_TEXT[i]]
    assert len(diff) == 1


def test_insert_missing_entry() -> None:
    out = settings_block.set_setting_value(SAMPLE_TEXT, 74, 0)
    assert settings_block.get_setting_value(out, 74) == 0
    # 原有条目仍在
    assert settings_block.get_setting_value(out, 87) == 1
    assert settings_block.get_setting_value(out, 12155) == 2


def test_extract_and_replace_block_roundtrip() -> None:
    block = settings_block.extract_map_block(SAMPLE_TEXT)
    # 改动后用旧块整体还原
    modified = settings_block.set_setting_value(SAMPLE_TEXT, 87, 0)
    modified = settings_block.set_setting_value(modified, 74, 0)  # 新增条目
    restored = settings_block.replace_map_block(modified, block)
    assert settings_block.extract_map_block(restored) == block
    # 还原后新增条目消失、改动回退
    assert settings_block.get_setting_value(restored, 87) == 1
    assert settings_block.get_setting_value(restored, 74) is None


def test_replace_block_keeps_outside_fields() -> None:
    block = settings_block.extract_map_block(SAMPLE_TEXT)
    modified = settings_block.set_setting_value(SAMPLE_TEXT, 87, 0)
    restored = settings_block.replace_map_block(modified, block)
    # 设置块以外的字段（HDRSettingRecordState）保持存在
    assert 'HDRSettingRecordState' in restored
