"""启动按钮定位助手的纯逻辑自检。"""

import unittest

from scripts.click_start_button import (
    OcrCandidate,
    is_point_in_rect,
    normalize_text,
    parse_window_handle,
    select_start_candidate,
)


class StartButtonHelperTest(unittest.TestCase):
    """验证文字、候选区域和坐标边界。"""

    def test_normalize_text_removes_spacing_and_decorations(self) -> None:
        """空白和火箭图标不应影响按钮文字匹配。"""
        self.assertEqual(normalize_text(' 启动 一条龙 🚀'), '启动一条龙')

    def test_parse_window_handle_accepts_decimal_and_hex(self) -> None:
        """窗口句柄应同时支持十进制和十六进制。"""
        self.assertEqual(parse_window_handle('16'), 16)
        self.assertEqual(parse_window_handle('0x10'), 16)

    def test_select_candidate_requires_exact_normalized_text(self) -> None:
        """包含额外文字的 OCR 行不得被当成启动按钮。"""
        exact = OcrCandidate('启动 一条龙 🚀', 500, 500, 120, 30)
        extra = OcrCandidate('不要启动一条龙', 520, 540, 140, 30)

        selected = select_start_candidate([extra, exact], 800, 700)

        self.assertEqual(selected, exact)
        self.assertIsNone(select_start_candidate([extra], 800, 700))

    def test_select_candidate_rejects_unsafe_geometry(self) -> None:
        """左上区域、越界候选和无效客户区都应拒绝。"""
        upper_left = OcrCandidate('启动一条龙', 10, 10, 120, 30)
        outside = OcrCandidate('启动一条龙', 750, 650, 120, 80)

        self.assertIsNone(select_start_candidate([upper_left], 800, 700))
        self.assertIsNone(select_start_candidate([outside], 800, 700))
        self.assertIsNone(select_start_candidate([upper_left], 0, 700))

    def test_point_in_rect_uses_right_and_bottom_exclusive_bounds(self) -> None:
        """矩形右边和下边不属于可点击区域。"""
        rect = (0, 0, 10, 10)

        self.assertTrue(is_point_in_rect(0, 0, rect))
        self.assertTrue(is_point_in_rect(9, 9, rect))
        self.assertFalse(is_point_in_rect(10, 9, rect))
        self.assertFalse(is_point_in_rect(9, 10, rect))


if __name__ == '__main__':
    unittest.main()
