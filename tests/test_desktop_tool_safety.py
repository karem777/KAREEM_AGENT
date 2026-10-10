import unittest
from unittest.mock import MagicMock, patch

from tools.desktop import DesktopTool


class DesktopToolSafetyTests(unittest.TestCase):
    def test_describe_exposes_desktop_observation_and_control(self):
        actions = DesktopTool().describe()["actions"]
        self.assertIn("screenshot", actions)
        self.assertIn("click", actions)
        self.assertIn("type_text", actions)
        self.assertIn("press", actions)

    def test_click_coordinates_are_checked_before_input(self):
        tool = DesktopTool()
        fake = MagicMock()
        fake.size.return_value = (100, 100)
        tool._pyautogui = fake
        result = tool.click(101, 20)
        self.assertFalse(result.get("success", True))
        fake.click.assert_not_called()

    def test_text_input_is_bounded(self):
        tool = DesktopTool()
        fake = MagicMock()
        tool._pyautogui = fake
        result = tool.type_text("x" * 5000)
        self.assertFalse(result.get("success", True))
        fake.write.assert_not_called()

    def test_empty_hotkey_is_rejected(self):
        tool = DesktopTool()
        fake = MagicMock()
        tool._pyautogui = fake
        result = tool.hotkey()
        self.assertFalse(result["success"])
        fake.hotkey.assert_not_called()

    def test_empty_app_command_is_rejected(self):
        tool = DesktopTool()
        with patch("tools.desktop.subprocess.Popen") as popen:
            result = tool.open_app("")
        self.assertFalse(result["success"])
        popen.assert_not_called()


if __name__ == "__main__":
    unittest.main()
