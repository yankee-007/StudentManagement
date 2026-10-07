"""Remark editing flow checks; no real desktop actions or contacts."""
import unittest
from types import SimpleNamespace
from unittest.mock import Mock, patch

from app.wecom_remark import AutomationConfig, Box, OCRItem, WeComRemarkChanger


class RemarkEditFlowTests(unittest.TestCase):
    def test_description_focus_is_used_without_another_input_click(self):
        header = OCRItem("示例学员/新生", 1.0, Box(400, 20, 520, 40))
        description = OCRItem("示例描述", 1.0, Box(400, 100, 520, 120))
        changer = object.__new__(WeComRemarkChanger)
        changer.config = AutomationConfig(restore_clipboard=False)
        changer.evidence_files = []
        changer._find_window = Mock(return_value=SimpleNamespace())
        changer._prepare_window_for_capture = Mock(return_value=(0, 0, False))
        changer._wait_for = Mock(side_effect=[
            (header, None, []),
            (description, None, []),
            ((header, header), None, []),
            (True, None, []),
            (header, None, []),
        ])
        actions = Mock()
        changer._click = actions.click
        changer._edit_remark = actions.edit

        with patch("app.wecom_remark.pyautogui.press") as press:
            result = changer.change_remark("示例学员/新生", "py175示例学员")

        self.assertTrue(result.success)
        self.assertEqual([call[0] for call in actions.mock_calls],
                         ["click", "click", "edit"])
        self.assertEqual(actions.click.call_args_list[1].args[1], description.box.center)
        actions.edit.assert_called_once_with("示例学员/新生", "py175示例学员")
        self.assertEqual([call.args[1] for call in changer._wait_for.call_args_list],
                         ["chat_verified", "contact_card", "edit_dialog",
                          "before_save_verified", "after_save_verified"])
        press.assert_called_once_with("enter")


if __name__ == "__main__":
    unittest.main()
