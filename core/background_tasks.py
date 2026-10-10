from __future__ import annotations

import threading
import time
import uuid
from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
from typing import Any, Callable

from core.report_writer import write_task_report


class BackgroundTaskQueue:
    """In-process background execution with isolated runners and durable TXT reports."""

    def __init__(self, runner_factory: Callable[[], Any], max_workers: int = 2):
        self.runner_factory = runner_factory
        self._executor = ThreadPoolExecutor(
            max_workers=max(1, int(max_workers)),
            thread_name_prefix="kareem-agent",
        )
        self._lock = threading.RLock()
        self._tasks: dict[str, dict[str, Any]] = {}

    def submit(self, message: str) -> dict[str, Any]:
        task_id = uuid.uuid4().hex
        with self._lock:
            self._tasks[task_id] = {
                "task_id": task_id,
                "goal": str(message),
                "status": "queued",
                "created_at": time.time(),
                "started_at": None,
                "finished_at": None,
                "result": None,
                "report_path": None,
                "error": None,
            }
            self._executor.submit(self._execute, task_id, str(message))
            return self._public(self._tasks[task_id])

    def _execute(self, task_id: str, message: str) -> None:
        started = time.time()
        with self._lock:
            task = self._tasks.get(task_id)
            if task is None:
                return
            task["status"] = "running"
            task["started_at"] = started

        try:
            # Each background task owns its runner; mutable planner/world state
            # is not shared with the synchronous web request or another task.
            runner = self.runner_factory()
            raw = runner.run(message, execution_mode="background")
            result = raw if isinstance(raw, dict) else {
                "success": False,
                "error": "Agent returned a non-object result.",
            }
            if result.get("needs_approval") or result.get("approval_required"):
                status = "needs_approval"
            else:
                status = "completed" if result.get("success") else "failed"
        except Exception as exc:
            result = {"success": False, "error": f"{type(exc).__name__}: {exc}"}
            status = "failed"

        finished = time.time()
        report_path = None
        try:
            report_path = write_task_report(
                task_id=task_id,
                goal=message,
                result=result,
                started_at=started,
                finished_at=finished,
            )
        except Exception as exc:
            result["report_error"] = f"{type(exc).__name__}: {exc}"

        with self._lock:
            task = self._tasks.get(task_id)
            if task is None:
                return
            task["status"] = status
            task["finished_at"] = finished
            task["result"] = result
            task["report_path"] = report_path
            task["error"] = result.get("error")

    def get(self, task_id: str) -> dict[str, Any] | None:
        with self._lock:
            task = self._tasks.get(str(task_id))
            return self._public(task) if task else None

    def list(self, limit: int = 20) -> list[dict[str, Any]]:
        with self._lock:
            tasks = sorted(self._tasks.values(), key=lambda x: x["created_at"], reverse=True)
            return [self._public(task) for task in tasks[:max(1, min(int(limit), 100))]]

    @staticmethod
    def _public(task: dict[str, Any]) -> dict[str, Any]:
        return deepcopy(task)
