import unittest

from core.ram_optimizer import is_ram_optimization_request, run_ram_review


class FakeWindowsTool:
    def __init__(self):
        self.closed = False

    def get_system_info(self):
        return {
            "success": True,
            "ram": {"total": 16 * 1024**3, "available": 2 * 1024**3, "percent": 87.5},
        }

    def processes(self, limit=50):
        return {
            "success": True,
            "processes": [
                {"pid": 123, "name": "browser.exe", "memory": 900 * 1024**2, "cpu": 4.0},
                {"pid": 456, "name": "editor.exe", "memory": 200 * 1024**2, "cpu": 1.0},
            ],
        }

    def close_process(self, *args, **kwargs):
        self.closed = True
        return {"success": True}


class FakeRegistry:
    def __init__(self):
        self.tool = FakeWindowsTool()

    def get(self, name):
        return self.tool if name == "windows" else None


class RamOptimizerTests(unittest.TestCase):
    def test_detects_arabic_and_english_ram_requests(self):
        self.assertTrue(is_ram_optimization_request("عايزك تنظف الرام"))
        self.assertTrue(is_ram_optimization_request("حرر الرام عندي"))
        self.assertTrue(is_ram_optimization_request("Please clean RAM"))
        self.assertFalse(is_ram_optimization_request("Explain what RAM means"))

    def test_reports_top_processes_without_changing_state(self):
        registry = FakeRegistry()
        result = run_ram_review(registry, "task-1", "نظف الرام")

        self.assertTrue(result["success"])
        self.assertEqual(result["observations"]["ram"]["percent"], 87.5)
        self.assertEqual(result["observations"]["top_processes"][0]["name"], "browser.exe")
        self.assertEqual(result["observations"]["top_processes"][0]["memory_mib"], 900.0)
        self.assertIn("لم أغلق أي برنامج", result["answer"])
        self.assertFalse(registry.tool.closed)

    def test_missing_windows_tool_fails_clearly(self):
        result = run_ram_review(object(), "task-2", "clean RAM")
        self.assertFalse(result["success"])
        self.assertIn("not registered", result["error"])


if __name__ == "__main__":
    unittest.main()
