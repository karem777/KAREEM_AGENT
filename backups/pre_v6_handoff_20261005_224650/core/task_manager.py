import json
from pathlib import Path
from datetime import datetime


class TaskManager:
    def __init__(self, path="data/tasks.json"):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)

        if not self.path.exists():
            self._save([])

    def _load(self):
        try:
            with self.path.open("r", encoding="utf-8") as f:
                data = json.load(f)

            return data if isinstance(data, list) else []

        except (FileNotFoundError, json.JSONDecodeError):
            return []

    def _save(self, tasks):
        with self.path.open("w", encoding="utf-8") as f:
            json.dump(
                tasks,
                f,
                ensure_ascii=False,
                indent=2
            )

    def create(self, goal):
        tasks = self._load()

        task = {
            "id": len(tasks) + 1,
            "goal": goal,
            "status": "active",
            "created_at": datetime.now().isoformat(),
            "steps": [],
            "reflection": []
        }

        tasks.append(task)
        self._save(tasks)

        return task

    def add_step(self, task_id, action, result):
        tasks = self._load()

        for task in tasks:
            if task["id"] == task_id:
                task["steps"].append({
                    "action": action,
                    "result": result,
                    "time": datetime.now().isoformat()
                })

                self._save(tasks)
                return task

        return None

    def reflect(self, task_id, reflection):
        tasks = self._load()

        for task in tasks:
            if task["id"] == task_id:
                task["reflection"].append({
                    "text": reflection,
                    "time": datetime.now().isoformat()
                })

                self._save(tasks)
                return task

        return None

    def complete(self, task_id):
        tasks = self._load()

        for task in tasks:
            if task["id"] == task_id:
                task["status"] = "completed"
                task["completed_at"] = datetime.now().isoformat()

                self._save(tasks)
                return task

        return None

    def active(self):
        return [
            task
            for task in self._load()
            if task.get("status") == "active"
        ]

    def get(self, task_id):
        for task in self._load():
            if task.get("id") == task_id:
                return task

        return None