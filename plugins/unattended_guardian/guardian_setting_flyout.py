"""顶号与未授权重登录熔断设置。"""
from typing import TYPE_CHECKING

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QDialog, QHBoxLayout, QVBoxLayout, QWidget
from qfluentwidgets import PrimaryPushButton, PushButton, SubtitleLabel

from one_dragon_qt.utils.config_utils import get_prop_adapter
from one_dragon_qt.widgets.app_setting.app_setting_flyout import AppSettingFlyout
from one_dragon_qt.widgets.setting_card.code_editor_setting_card import CodeEditor
from one_dragon_qt.widgets.setting_card.push_setting_card import PushSettingCard
from one_dragon_qt.widgets.setting_card.spin_box_setting_card import SpinBoxSettingCard
from one_dragon_qt.widgets.setting_card.switch_setting_card import SwitchSettingCard

from .unattended_guardian_config import get_config, keywords_to_text, text_to_keywords

if TYPE_CHECKING:
    from zzz_od.context.zzz_context import ZContext


class KeywordEditorDialog(QDialog):
    """独立的关键词编辑弹窗，不受 TeachingTip 悬浮层尺寸影响。"""

    def __init__(
        self,
        parent: QWidget | None,
        initial_code: str,
    ) -> None:
        QDialog.__init__(self, parent)
        self.setWindowTitle('编辑顶号识别关键词')
        self.setWindowModality(Qt.WindowModality.WindowModal)
        self.setFixedSize(660, 520)

        self.title_label = SubtitleLabel('编辑顶号识别关键词', self)
        self.editor = CodeEditor(self)
        self.editor.setPlaceholderText('一行一个关键词，任意一个命中即触发顶号冷却')
        self.editor.setPlainText(initial_code)

        self.cancelButton = PushButton('取消', self)
        self.yesButton = PrimaryPushButton('确定', self)
        self.cancelButton.setFixedWidth(120)
        self.yesButton.setFixedWidth(120)
        self.cancelButton.clicked.connect(self.reject)
        self.yesButton.clicked.connect(self.accept)

        button_layout = QHBoxLayout()
        button_layout.setSpacing(12)
        button_layout.addStretch()
        button_layout.addWidget(self.cancelButton)
        button_layout.addWidget(self.yesButton)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 24, 24, 20)
        layout.setSpacing(16)
        layout.addWidget(self.title_label)
        layout.addWidget(self.editor, 1)
        layout.addLayout(button_layout)

    def get_text(self) -> str:
        """返回编辑器文本。"""
        return self.editor.toPlainText()


class GuardianSettingFlyout(AppSettingFlyout):
    """顶号检测设置。"""

    def __init__(
        self,
        ctx: 'ZContext',
        group_id: str,
        parent: QWidget | None = None,
    ) -> None:
        # TeachingTip.make 会重新挂载内容视图，届时 self.window() 变成狭窄的悬浮层。
        # 保留真正的主窗口，关键词编辑弹窗必须以它为父级，否则底部按钮会被裁掉。
        self._dialog_parent: QWidget | None = parent.window() if parent is not None else None
        AppSettingFlyout.__init__(self, ctx, group_id, parent)

    def _setup_ui(self, layout: QVBoxLayout) -> None:
        self.detect_enabled = SwitchSettingCard(
            icon='',
            title='顶号与重登录熔断',
            content='同时检测顶号弹窗、运行中登录页与登录 SDK 二次初始化',
            margins=self.card_margins,
        )
        layout.addWidget(self.detect_enabled)

        self.check_interval = SpinBoxSettingCard(
            icon='',
            title='检测间隔（秒）',
            content='顶号弹窗 OCR 间隔；登录页熔断始终逐帧执行，建议保持 1 秒',
            minimum=1,
            maximum=60,
            margins=self.card_margins,
        )
        layout.addWidget(self.check_interval)

        self.kicked_keywords = PushSettingCard(
            icon='',
            title='顶号识别关键词',
            text='编辑',
            content='',
            margins=self.card_margins,
        )
        self.kicked_keywords.clicked.connect(self._on_edit_keywords)
        layout.addWidget(self.kicked_keywords)

        self.kicked_cooldown = SpinBoxSettingCard(
            icon='',
            title='顶号冷却（分钟）',
            content='冷却结束前，插件与外部恢复脚本都不会重新登录',
            minimum=1,
            maximum=720,
            margins=self.card_margins,
        )
        layout.addWidget(self.kicked_cooldown)

    def init_config(self) -> None:
        config = get_config()
        self.detect_enabled.init_with_adapter(get_prop_adapter(config, 'detect_enabled'))
        self.check_interval.init_with_adapter(get_prop_adapter(config, 'check_interval_seconds'))
        self.kicked_cooldown.init_with_adapter(get_prop_adapter(config, 'kicked_cooldown_minutes'))
        self._refresh_keywords_preview()

    def _on_edit_keywords(self) -> None:
        config = get_config()
        dialog = KeywordEditorDialog(
            parent=self._dialog_parent or self.window(),
            initial_code=keywords_to_text(config.kicked_keywords),
        )
        if dialog.exec():
            config.kicked_keywords = text_to_keywords(dialog.get_text())
            self._refresh_keywords_preview()

    def _refresh_keywords_preview(self) -> None:
        keywords = get_config().kicked_keywords
        preview = ' / '.join(keywords[:2])
        if len(keywords) > 2:
            preview += f' 等 {len(keywords)} 个'
        self.kicked_keywords.setContent(preview)
