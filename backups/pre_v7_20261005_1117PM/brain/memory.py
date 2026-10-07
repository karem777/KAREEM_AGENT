import json
from pathlib import Path


class Memory:
    def __init__(self, path="data/memory.json"):
        self.path = Path(path)

        # Make sure the parent directory exists
        self.path.parent.mkdir(parents=True, exist_ok=True)

        # Create memory file if it doesn't exist
        if not self.path.exists():
            self._save({})

    def _load(self):
        try:
            with self.path.open("r", encoding="utf-8") as f:
                data = json.load(f)

            if isinstance(data, dict):
                return data

            return {}

        except (FileNotFoundError, json.JSONDecodeError):
            return {}

    def _save(self, data):
        with self.path.open("w", encoding="utf-8") as f:
            json.dump(
                data,
                f,
                ensure_ascii=False,
                indent=2
            )

    def set(self, key, value):
        data = self._load()

        data[key] = value

        self._save(data)

        return {
            "success": True,
            "key": key,
            "value": value
        }

    def get(self, key):
        data = self._load()

        if key not in data:
            return {
                "success": False,
                "error": f"Memory not found: {key}"
            }

        return {
            "success": True,
            "key": key,
            "value": data[key]
        }

    def delete(self, key):
        data = self._load()

        if key not in data:
            return {
                "success": False,
                "error": f"Memory not found: {key}"
            }

        del data[key]

        self._save(data)

        return {
            "success": True,
            "result": f"Memory deleted: {key}"
        }

    def all(self):
        return {
            "success": True,
            "memory": self._load()
        }

    def clear(self):
        self._save({})

        return {
            "success": True,
            "result": "Memory cleared"
        }