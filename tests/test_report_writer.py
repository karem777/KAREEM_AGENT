from pathlib import Path

from core.report_writer import write_task_report


def test_report_writer_creates_readable_report_and_redacts_secrets(tmp_path):
    result = {
        "success": True,
        "answer": "Done. api_key=abc123",
        "steps": 3,
        "evidence": [
            {"tool": "filesystem", "action": "write_file", "result": {"success": True}},
        ],
    }
    path = Path(write_task_report("task-1", "Create a file", result, desktop_dir=tmp_path))
    text = path.read_text(encoding="utf-8")
    assert path.parent == tmp_path
    assert "Create a file" in text
    assert "filesystem.write_file" in text
    assert "abc123" not in text
    assert "[REDACTED]" in text
