import sys
import types
import unittest
from unittest.mock import patch

from tools.windows_complete import WindowsTool


class FakeProcess:
    def __init__(self, pid, name, username="user"):
        self.info = {"pid": pid, "name": name, "username": username}
        self.terminated = False

    def terminate(self):
        self.terminated = True

    def wait(self, timeout=None):
        return 0

    def is_running(self):
        return not self.terminated


class WindowsProcessGuardTests(unittest.TestCase):
    def test_requires_confirmation_before_process_query(self):
        result = WindowsTool().close_process("notepad.exe")
        self.assertFalse(result["success"])
        self.assertTrue(result["approval_required"])

    def test_refuses_to_terminate_core_windows_process(self):
        process = FakeProcess(111, "svchost.exe", "NT AUTHORITY\\SYSTEM")
        fake_psutil = types.SimpleNamespace(
            process_iter=lambda fields: [process],
            NoSuchProcess=RuntimeError,
            AccessDenied=PermissionError,
            TimeoutExpired=TimeoutError,
        )
        with patch.dict(sys.modules, {"psutil": fake_psutil}):
            result = WindowsTool().close_process("111", confirm=True)
        self.assertFalse(result["success"])
        self.assertTrue(result["blocked"])
        self.assertFalse(process.terminated)


if __name__ == "__main__":
    unittest.main()
