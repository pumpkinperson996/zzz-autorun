from one_dragon.base.config.yaml_config import YamlConfig

from . import unattended_guardian_const as const


def keywords_to_text(keywords: list[str]) -> str:
    """将关键词列表转换为一行一个关键词的编辑文本。"""
    return '\n'.join(keywords)


def text_to_keywords(text: str) -> list[str]:
    """解析关键词编辑文本，去除空行并按原顺序去重。"""
    seen: set[str] = set()
    result: list[str] = []
    for line in text.splitlines():
        keyword = line.strip()
        if keyword and keyword not in seen:
            seen.add(keyword)
            result.append(keyword)
    return result


class UnattendedGuardianConfig(YamlConfig):
    """顶号检测的全局配置，落盘到 config/unattended_guardian.yml。"""

    def __init__(self) -> None:
        YamlConfig.__init__(self, module_name=const.APP_ID)

    @property
    def detect_enabled(self) -> bool:
        """顶号检测总开关。"""
        return self.get('detect_enabled', True)

    @detect_enabled.setter
    def detect_enabled(self, new_value: bool) -> None:
        self.update('detect_enabled', new_value)

    @property
    def check_interval_seconds(self) -> int:
        """两次顶号 OCR 检测之间的最短间隔。"""
        return max(1, self.get('check_interval_seconds', 1))

    @check_interval_seconds.setter
    def check_interval_seconds(self, new_value: int) -> None:
        self.update('check_interval_seconds', new_value)

    @property
    def kicked_keywords(self) -> list[str]:
        """顶号弹窗关键词，任一命中即算一次命中。"""
        value = self.get('kicked_keywords', None)
        if value:
            return value
        legacy = self.get('kicked_keywords_str', '')
        if legacy:
            keywords = [keyword.strip() for keyword in legacy.split(',') if keyword.strip()]
            if keywords:
                return keywords
        return list(const.DEFAULT_KICKED_KEYWORDS)

    @kicked_keywords.setter
    def kicked_keywords(self, new_value: list[str]) -> None:
        self.update('kicked_keywords', new_value or list(const.DEFAULT_KICKED_KEYWORDS))

    @property
    def kicked_cooldown_minutes(self) -> int:
        """被顶号后允许外部脚本恢复运行前的等待时长。"""
        return max(1, self.get('kicked_cooldown_minutes', 120))

    @kicked_cooldown_minutes.setter
    def kicked_cooldown_minutes(self, new_value: int) -> None:
        self.update('kicked_cooldown_minutes', new_value)


_config: UnattendedGuardianConfig | None = None


def get_config() -> UnattendedGuardianConfig:
    """获取全局配置单例。"""
    global _config
    if _config is None:
        _config = UnattendedGuardianConfig()
    return _config
