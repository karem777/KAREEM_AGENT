import json
import unittest

from core.system_diagnostic import is_system_diagnostic_request, run_system_diagnostic


class FakeWindowsTool:
    def get_system_info(self):
        return {
            "success": True,
            "ram": {"total": 16, "available": 1, "percent": 93},
            "system_drive": {"total": 100, "free": 4, "used": 96},
        }

    def processes(self, limit=20):
        return {"success": True, "processes": [{"name": "python.exe"}]}

    def storage(self):
        return {
            "success": True,
            "stdout": json.dumps([{"DriveLetter": "C", "HealthStatus": "Healthy"}]),
            "stderr": "",
        }

    def network(self):
        return {
            "success": True,
            "stdout": json.dumps({"adapters": [{"Name": "Wi-Fi", "Status": "Up"}], "config": []}),
            "stderr": "",
        }

    def events(self, log_name="System", hours=24, limit=60):
        return {
            "success": True,
            "stdout": json.dumps([
                {"LevelDisplayName": "Critical", "Id": 100},
                {"LevelDisplayName": "Error", "Id": 200},
            ]),
            "stderr": "",
        }


class FakeRegistry:
    def __init__(self):
        self.tool = FakeWindowsTool()

    def get(self, name):
        return self.tool if name == "windows" else None


class SystemDiagnosticTests(unittest.TestCase):
    def test_detects_arabic_and_english_diagnostic_requests(self):
        self.assertTrue(is_system_diagnostic_request("عايزك تفحص الجهاز وتقيمه من 100"))
        self.assertTrue(is_system_diagnostic_request("افحص جهازي بالكامل، وقيّم حالته من 100"))
        self.assertTrue(is_system_diagnostic_request("Please run a system diagnostic"))
        self.assertFalse(is_system_diagnostic_request("Explain what RAM means"))

    def test_returns_evidence_based_score_and_observations(self):
        result = run_system_diagnostic(FakeRegistry(), "test-task", "افحص الجهاز")

        self.assertTrue(result["success"])
        self.assertEqual(result["score"], 59)
        self.assertEqual(result["checks_completed"], 5)
        self.assertEqual(result["checks_total"], 5)
        self.assertEqual(result["task_id"], "test-task")
        self.assertEqual(len(result["evidence"]), 5)
        self.assertIn("system", result["observations"])
        self.assertTrue(any("RAM usage is high" in item["finding"] for item in result["findings"]))

    def test_missing_windows_tool_fails_clearly(self):
        result = run_system_diagnostic(object(), "test-task", "check my pc")
        self.assertFalse(result["success"])
        self.assertIsNone(result["score"])
        self.assertIn("not registered", result["error"])


if __name__ == "__main__":
    unittest.main()
