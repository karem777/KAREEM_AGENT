from __future__ import annotations

import shutil
import time
from pathlib import Path

from engineering.engineer import Engineer


class SelfRepair:
    def __init__(self, project_root: str | Path, backup_root: str | Path = "backups"):
        self.root = Path(project_root).resolve()
        self.backups = Path(backup_root).resolve()
        self.backups.mkdir(parents=True, exist_ok=True)
        self.engineer = Engineer(self.root)

    def diagnose(self):
        return {
            "success": True,
            "project": str(self.root),
            "python": self.engineer.run_tests(),
            "key_files": {
                rel: (self.root / rel).exists()
                for rel in [
                    "app.py",
                    "brain/planner.py",
                    "brain/local_brain.py",
                    "core/runner.py",
                    "tools/registry.py",
                    "tools/browser.py",
                ]
            },
        }

    def backup_project(self, paths: list[str] | None = None):
        stamp = time.strftime("%Y%m%d_%H%M%S")
        dest = self.backups / f"repair_{stamp}"
        dest.mkdir(parents=True, exist_ok=True)
        selected = paths or [
            "brain/planner.py", "core/runner.py", "tools/registry.py", "tools/browser.py",
        ]
        copied = []
        for rel in selected:
            src = (self.root / rel).resolve()
            if src.exists() and self.root in src.parents:
                out = dest / rel
                out.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(src, out)
                copied.append(rel)
        return {"success": True, "backup": str(dest), "copied": copied}

    def apply_patch(self, path: str, old: str, new: str, replace_all: bool = False):
        return self.engineer.apply_patch(path, old, new, replace_all=replace_all)

    def run_tests(self, target: str = ""):
        return self.engineer.run_tests(target)
