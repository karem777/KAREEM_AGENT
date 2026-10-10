import time

from core.background_tasks import BackgroundTaskQueue


def test_background_queue_runs_isolated_task_and_records_report(monkeypatch):
    monkeypatch.setattr(
        "core.background_tasks.write_task_report",
        lambda **kwargs: "C:/Users/test/Desktop/KAREEM_AGENT_Report.txt",
    )

    class FakeRunner:
        def run(self, message, execution_mode="visible"):
            assert message == "make a test file"
            assert execution_mode == "background"
            return {
                "success": True,
                "mode": "task",
                "answer": "Done",
                "steps": 2,
                "evidence": [],
            }

    queue = BackgroundTaskQueue(FakeRunner, max_workers=1)
    submitted = queue.submit("make a test file")
    task_id = submitted["task_id"]

    deadline = time.time() + 5
    state = queue.get(task_id)
    while state and state["status"] in {"queued", "running"} and time.time() < deadline:
        time.sleep(0.02)
        state = queue.get(task_id)

    assert state is not None
    assert state["status"] == "completed"
    assert state["report_path"].endswith("KAREEM_AGENT_Report.txt")
    assert state["result"]["success"] is True
