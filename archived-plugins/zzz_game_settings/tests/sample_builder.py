"""构造合成的 GENERAL_DATA.bin 样例，用于离线测试（不依赖真实游戏文件）。

样例明文前置一大段空格，确保按列取众数破解密钥时每列众数都是空格，从而
GeneralData.parse 能稳定还原出编码时使用的任意密钥。
"""
from plugins.zzz_game_settings.general_data_codec import _KEY_LEN, _write_varint

# 一段仿游戏原生对齐风格的 JSON（缩进用空格，冒号两侧留空格）
SAMPLE_TEXT = (
    ' ' * (_KEY_LEN * 40)  # 前置空格，保证列众数为空格
    + '\n{\n'
    '    "$Type" : "MoleMole.GeneralLocalDataItem",\n'
    '    "deviceUUID" : "",\n'
    '    "SystemSettingDataMap" : {\n'
    '        "87" : {\n'
    '            "$Type" : "MoleMole.SystemSettingLocalData",\n'
    '            "Version" : 0,\n'
    '            "Data" : 1\n'
    '        },\n'
    '        "110" : {\n'
    '            "$Type" : "MoleMole.SystemSettingLocalData",\n'
    '            "Version" : 0,\n'
    '            "Data" : 1\n'
    '        },\n'
    '        "12155" : {\n'
    '            "$Type" : "MoleMole.SystemSettingLocalData",\n'
    '            "Version" : 0,\n'
    '            "Data" : 2\n'
    '        }\n'
    '    },\n'
    '    "HDRSettingRecordState" : 0\n'
    '}'
)

# 用于编码的合成密钥（任意 22 个不同字节值均可，会被列众数破解还原）
SAMPLE_KEY = [(0x30 + i) for i in range(_KEY_LEN)]


def build_sample_bytes(text: str = SAMPLE_TEXT, key: list[int] | None = None) -> bytes:
    """把明文按 codec 规则编码为完整文件字节。"""
    if key is None:
        key = SAMPLE_KEY
    prefix = bytearray(22)
    prefix[17] = 0x06  # BinaryObjectString 记录类型
    enc_str = ''.join(chr(ord(c) ^ key[i % _KEY_LEN]) for i, c in enumerate(text))
    payload = enc_str.encode('utf-8')
    return bytes(prefix) + _write_varint(len(payload)) + payload + b'\x0b'
