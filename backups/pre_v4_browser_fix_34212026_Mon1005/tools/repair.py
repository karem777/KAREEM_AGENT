from __future__ import annotations

from repair.self_repair import SelfRepair


class RepairTool:
    name = "repair"
    description = "Diagnose and repair the agent itself with backup + verification."

    def __init__(self, project_root: str, backup_root: str = "backups"):
        self.repair = SelfRepair(project_root, backup_root)

    def diagnose_agent(self):
        return self.repair.diagnose()

    def backup_project(self, paths=None):
        return self.repair.backup_project(paths)

    def apply_patch(self, path: str, old: str, new: str, replace_all: bool = False):
        return self.repair.apply_patch(path, old, new, replace_all=replace_all)

    def run_tests(self, target: str = ""):
        return self.repair.run_tests(target)

    def describe(self):
        return {
            "name": self.name,
            "description": self.description,
            "actions": {
                "diagnose_agent": {"description": "Inspect the agent and run validation.", "parameters": {}},
                "backup_project": {"description": "Backup critical agent files before repair.", "parameters": {"paths": {"type": "array", "required": False}}},
                "apply_patch": {"description": "Apply an exact source patch.", "parameters": {"path": {"type": "string", "required": True}, "old": {"type": "string", "required": True}, "new": {"type": "string", "required": True}, "replace_all": {"type": "boolean", "required": False, "default": False}}},
                "run_tests": {"description": "Run repair verification tests.", "parameters": {"target": {"type": "string", "required": False, "default": ""}}},
            },
        }
