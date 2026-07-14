"""GENERAL_DATA.bin 的编解码。

文件三层结构（2026-07-03 实测）：
1. .NET BinaryFormatter 单字符串记录：17 字节 SerializationHeader + 0x06(BinaryObjectString)
   + 4 字节 objectId + 7bit 变长长度 + UTF-8 载荷 + 0x0b(MessageEnd)。
2. 载荷解码为 UTF-8 字符串后，逐字符（按码点）循环 XOR 一个 22 字符密钥。
   密钥是 `UnityEngine.GameObject` 的同形字变体，本模块用列众数频率分析动态破解，
   不硬编码，以便密钥或格式变化时自检自然失败并安全放弃。
3. 解密后是带对齐空格的自定义风格 JSON，游戏设置在 SystemSettingDataMap。
"""
from collections import Counter

_RECORD_TYPE_STRING: int = 0x06
_MESSAGE_END: int = 0x0B
_PREFIX_LEN: int = 22  # 17 字节头 + 1 字节记录类型 + 4 字节 objectId
_KEY_LEN: int = 22


class GeneralDataFormatError(Exception):
    """文件格式与预期不符（游戏版本可能已更新）。"""


def _read_varint(data: bytes, pos: int) -> tuple[int, int]:
    """从 pos 处读 .NET 7bit 变长整数，返回 (值, 结束位置)。"""
    length = 0
    shift = 0
    while True:
        if pos >= len(data):
            raise GeneralDataFormatError('读取长度时越界')
        b = data[pos]
        pos += 1
        length |= (b & 0x7F) << shift
        if not (b & 0x80):
            break
        shift += 7
        if shift > 35:
            raise GeneralDataFormatError('长度字段异常')
    return length, pos


def _write_varint(value: int) -> bytes:
    out = bytearray()
    while True:
        b = value & 0x7F
        value >>= 7
        if value:
            out.append(b | 0x80)
        else:
            out.append(b)
            break
    return bytes(out)


def _crack_key(code_points: list[int]) -> list[int]:
    """列众数频率破解：假设每个密钥位对应的明文众数字符为空格(0x20)。"""
    if len(code_points) < _KEY_LEN:
        raise GeneralDataFormatError('载荷过短，无法破解密钥')
    return [
        Counter(code_points[k::_KEY_LEN]).most_common(1)[0][0] ^ 0x20
        for k in range(_KEY_LEN)
    ]


class GeneralData:
    """一次解析的结果，持有明文文本与还原字节所需的全部信息。"""

    def __init__(self, prefix: bytes, key: list[int], text: str, suffix: bytes):
        self.prefix: bytes = prefix
        """固定前缀（头 + 记录类型 + objectId），编码时原样复用。"""
        self.key: list[int] = key
        """XOR 密钥，编码时复用以保证与源文件一致。"""
        self.text: str = text
        """解密后的 JSON 文本。"""
        self.suffix: bytes = suffix
        """尾部字节（MessageEnd），编码时原样复用。"""

    @classmethod
    def parse(cls, raw: bytes) -> 'GeneralData':
        """解析原始文件字节。格式不符时抛 GeneralDataFormatError。"""
        if len(raw) < _PREFIX_LEN + 2:
            raise GeneralDataFormatError('文件过短')
        if raw[17] != _RECORD_TYPE_STRING:
            raise GeneralDataFormatError('未找到 BinaryObjectString 记录')

        length, pos = _read_varint(raw, _PREFIX_LEN)
        payload = raw[pos:pos + length]
        if len(payload) != length:
            raise GeneralDataFormatError('载荷长度不足')
        suffix = raw[pos + length:]
        if suffix != bytes([_MESSAGE_END]):
            raise GeneralDataFormatError('文件尾不是 MessageEnd(0x0b)')

        try:
            code_points = [ord(c) for c in payload.decode('utf-8')]
        except UnicodeDecodeError as e:
            raise GeneralDataFormatError('载荷不是合法 UTF-8') from e

        key = _crack_key(code_points)
        text = ''.join(
            chr(cp ^ key[i % _KEY_LEN]) for i, cp in enumerate(code_points)
        )
        return cls(prefix=raw[:_PREFIX_LEN], key=key, text=text, suffix=suffix)

    def encode(self, new_text: str | None = None) -> bytes:
        """把文本（默认 self.text）编码回完整文件字节。"""
        text = self.text if new_text is None else new_text
        enc_str = ''.join(
            chr(ord(c) ^ self.key[i % _KEY_LEN]) for i, c in enumerate(text)
        )
        payload = enc_str.encode('utf-8')
        return self.prefix + _write_varint(len(payload)) + payload + self.suffix


def verify_roundtrip(raw: bytes) -> bool:
    """往返自检：解码再原样编码是否与源文件逐字节一致。

    这是一切写盘的前置门槛：不一致说明格式或密钥已变化，必须放弃写入。
    """
    try:
        data = GeneralData.parse(raw)
    except GeneralDataFormatError:
        return False
    return data.encode() == raw
