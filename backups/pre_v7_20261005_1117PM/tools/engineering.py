from __future__ import annotations

from engineering.engineer import Engineer


class EngineeringTool:
    name = "engineering"
    description = "Inspect, edit, test and repair the KAREEM_AGENT codebase."

    def __init__(self, project_root: str):
        self.engineer = Engineer(project_root)

    def project_map(self, max_files: int = 300):
        return self.engineer.project_map(max_files=max_files)

    def search_code(self, query: str, max_results: int = 30):
        return self.engineer.search_code(query, max_results=max_results)

    def read_file(self, path: str, max_chars: int = 30000):
        return self.engineer.read_file(path, max_chars=max_chars)

    def write_file(self, path: str, content: str):
        return self.engineer.write_file(path, content)

    def apply_patch(self, path: str, old: str, new: str, replace_all: bool = False):
        return self.engineer.apply_patch(path, old, new, replace_all=replace_all)

    def diff(self, path: str, old: str, new: str):
        return self.engineer.diff(path, old, new)

    def run_tests(self, target: str = ""):
        return self.engineer.run_tests(target)

    def describe(self):
        return {
            "name": self.name,
            "description": self.description,
            "actions": {
                "project_map": {"description": "Map the local project.", "parameters": {"max_files": {"type": "integer", "required": False, "default": 300}}},
                "search_code": {"description": "Search source code for a symbol/text.", "parameters": {"query": {"type": "string", "required": True}, "max_results": {"type": "integer", "required": False, "default": 30}}},
                "read_file": {"description": "Read a project file.", "parameters": {"path": {"type": "string", "required": True}, "max_chars": {"type": "integer", "required": False, "default": 30000}}},
                "write_file": {"description": "Write a project file.", "parameters": {"path": {"type": "string", "required": True}, "content": {"type": "string", "required": True}}},
                "apply_patch": {"description": "Apply an exact text patch.", "parameters": {"path": {"type": "string", "required": True}, "old": {"type": "string", "required": True}, "new": {"type": "string", "required": True}, "replace_all": {"type": "boolean", "required": False, "default": False}}},
                "diff": {"description": "Show a unified diff.", "parameters": {"path": {"type": "string", "required": True}, "old": {"type": "string", "required": True}, "new": {"type": "string", "required": True}}},
                "run_tests": {"description": "Run project tests or syntax validation.", "parameters": {"target": {"type": "string", "required": False, "default": ""}}},
            },
        }
