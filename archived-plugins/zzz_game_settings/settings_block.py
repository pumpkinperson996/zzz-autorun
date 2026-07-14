"""SystemSettingDataMap 文本块的外科手术。

所有操作都在解密后的 JSON 文本上做字符串级替换，绝不整体重序列化 JSON——
游戏使用带对齐空格的自定义风格，重排会偏离原生格式、破坏往返一致性。
"""
import re

from .general_data_codec import GeneralDataFormatError

# 匹配 SystemSettingDataMap 的键与其整个 {...} 值块（假设块内不再嵌套花括号，实测成立）
_MAP_BLOCK_RE = re.compile(
    r'"SystemSettingDataMap"\s*:\s*(\{[^{}]*(?:\{[^{}]*\}[^{}]*)*\})',
    re.S,
)


def _find_map_block(text: str) -> re.Match:
    m = _MAP_BLOCK_RE.search(text)
    if m is None:
        raise GeneralDataFormatError('未找到 SystemSettingDataMap 块')
    return m


def extract_map_block(text: str) -> str:
    """截取 SystemSettingDataMap 的值块文本（含外层花括号），用作快照。"""
    return _find_map_block(text).group(1)


def replace_map_block(text: str, block: str) -> str:
    """把当前 SystemSettingDataMap 的值块整体替换为给定块（快照还原用）。"""
    m = _find_map_block(text)
    return text[:m.start(1)] + block + text[m.end(1):]


def _entry_re(setting_id: int) -> re.Pattern:
    # 匹配某个 id 条目内的 "Data" : <数字>，捕获前缀与数字，便于只替换数字
    return re.compile(
        rf'("{setting_id}"\s*:\s*\{{[^{{}}]*?"Data"\s*:\s*)(-?\d+)',
        re.S,
    )


def get_setting_value(text: str, setting_id: int) -> int | None:
    """读取某设置项当前值；不存在返回 None。"""
    m = _entry_re(setting_id).search(text)
    return int(m.group(2)) if m else None


def set_setting_value(text: str, setting_id: int, value: int) -> str:
    """把某设置项的 Data 改为 value；条目不存在则按原生风格插入到块内首位。"""
    pattern = _entry_re(setting_id)
    m = pattern.search(text)
    if m is not None:
        return text[:m.start(2)] + str(value) + text[m.end(2):]
    return _insert_entry(text, setting_id, value)


def _insert_entry(text: str, setting_id: int, value: int) -> str:
    """在 SystemSettingDataMap 块开头插入一个新条目，模仿相邻条目的缩进风格。"""
    block_match = _find_map_block(text)
    block = block_match.group(1)

    # 探测块内现有条目的缩进与内层风格，尽量与原生一致
    sample = re.search(
        r'\n(\s*)"-?\d+"\s*:\s*\{(.*?)\}\s*(,?)', block, re.S
    )
    if sample is not None:
        indent = sample.group(1)
        inner = sample.group(2)
    else:
        indent = '\t\t\t'
        inner = (
            '\n\t\t\t\t"$Type" : "MoleMole.SystemSettingLocalData",'
            '\n\t\t\t\t"Version" : 0,'
            '\n\t\t\t\t"Data" : 0\n\t\t\t'
        )

    new_inner = re.sub(r'("Data"\s*:\s*)(-?\d+)', rf'\g<1>{value}', inner)
    if new_inner == inner:  # 样本里没有 Data 字段兜底
        new_inner = (
            '\n\t\t\t\t"$Type" : "MoleMole.SystemSettingLocalData",'
            '\n\t\t\t\t"Version" : 0,'
            f'\n\t\t\t\t"Data" : {value}\n\t\t\t'
        )

    entry = f'"{setting_id}" : {{{new_inner}}}'

    open_brace = block_match.start(1)  # '{' 在 text 中的位置
    # 判断块是否为空：{ 之后到 } 只有空白
    body = block[1:-1]
    if body.strip() == '':
        tail_indent = indent[:-1] if indent else ''
        new_block = f'{{\n{indent}{entry}\n{tail_indent}}}'
        return text[:block_match.start(1)] + new_block + text[block_match.end(1):]

    insert_pos = open_brace + 1
    return (
        text[:insert_pos]
        + '\n' + indent + entry + ','
        + text[insert_pos:]
    )
