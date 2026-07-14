"""GENERAL_DATA.bin 编解码与往返自检测试。"""
import pytest

from plugins.zzz_game_settings.general_data_codec import (
    GeneralData,
    GeneralDataFormatError,
    verify_roundtrip,
)
from plugins.zzz_game_settings.tests.sample_builder import (
    SAMPLE_TEXT,
    build_sample_bytes,
)


def test_parse_recovers_text() -> None:
    raw = build_sample_bytes()
    data = GeneralData.parse(raw)
    assert data.text == SAMPLE_TEXT


def test_encode_is_byte_identical() -> None:
    raw = build_sample_bytes()
    data = GeneralData.parse(raw)
    assert data.encode() == raw


def test_verify_roundtrip_true_for_valid() -> None:
    assert verify_roundtrip(build_sample_bytes()) is True


def test_verify_roundtrip_false_for_corrupted_tail() -> None:
    raw = bytearray(build_sample_bytes())
    raw[-1] = 0x00  # 破坏 MessageEnd
    assert verify_roundtrip(bytes(raw)) is False


def test_parse_rejects_wrong_record_type() -> None:
    raw = bytearray(build_sample_bytes())
    raw[17] = 0x05  # 非 BinaryObjectString
    with pytest.raises(GeneralDataFormatError):
        GeneralData.parse(bytes(raw))


def test_edited_value_roundtrips() -> None:
    raw = build_sample_bytes()
    data = GeneralData.parse(raw)
    new_text = data.text.replace('"Data" : 1', '"Data" : 0', 1)
    re_encoded = data.encode(new_text)
    assert GeneralData.parse(re_encoded).text == new_text
