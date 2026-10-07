from brain.memory import Memory


class MemoryTool:
    name = "memory"
    description = "Store, retrieve, delete, list, and clear long-term agent memory."

    def __init__(self, memory=None):
        self.memory = memory if memory is not None else Memory()

    def set(self, key, value):
        return self.memory.set(key, value)

    def get(self, key):
        return self.memory.get(key)

    def delete(self, key):
        return self.memory.delete(key)

    def all(self):
        return self.memory.all()

    def clear(self):
        return self.memory.clear()

    def describe(self):
        return {
            "name": self.name,
            "description": self.description,
            "actions": {
                "set": {
                    "description": "Store a value in long-term memory.",
                    "parameters": {
                        "key": {
                            "type": "string",
                            "required": True
                        },
                        "value": {
                            "type": "string",
                            "required": True
                        }
                    }
                },
                "get": {
                    "description": "Retrieve a value from long-term memory.",
                    "parameters": {
                        "key": {
                            "type": "string",
                            "required": True
                        }
                    }
                },
                "delete": {
                    "description": "Delete a memory by key.",
                    "parameters": {
                        "key": {
                            "type": "string",
                            "required": True
                        }
                    }
                },
                "all": {
                    "description": "Return all stored memories.",
                    "parameters": {}
                },
                "clear": {
                    "description": "Clear all long-term memories.",
                    "parameters": {}
                }
            }
        }