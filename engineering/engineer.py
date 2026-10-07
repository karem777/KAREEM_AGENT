from __future__ import annotations

import difflib
import re
import subprocess
from pathlib import Path
from typing import Iterable


class Engineer:
    def __init__(self, project_root: str | Path):
        self.root = Path(project_root).resolve()

    def _safe(self, path: str | Path) -> Path:
        p = Path(path)
        target = p.resolve() if p.is_absolute() else (self.root / p).resolve()
        if target != self.root and self.root not in target.parents:
            raise PermissionError("Project path is outside KAREEM_AGENT project root")
        return target

    def project_map(self, max_files: int = 300):
        rows = []
        for p in self.root.rglob("*"):
            if len(rows) >= max_files:
                break
            if not p.is_file() or ".venv" in p.parts or "__pycache__" in p.parts:
                continue
            rows.append(str(p.relative_to(self.root)))
        return {"success": True, "root": str(self.root), "files": rows}

    def search_code(self, query: str, max_results: int = 30):
        q = str(query or "").strip()
        out = []
        if not q:
            return {"success": False, "error": "Empty query"}
        for p in self.root.rglob("*"):
            if len(out) >= max_results:
                break
            if not p.is_file() or ".venv" in p.parts or "__pycache__" in p.parts:
                continue
            if p.suffix.lower() not in {".py", ".js", ".ts", ".tsx", ".json", ".md", ".txt", ".html", ".css", ".ps1", ".yaml", ".yml"}:
                continue
            try:
                text = p.read_text(encoding="utf-8", errors="ignore")
            except Exception:
                continue
            for i, line in enumerate(text.splitlines(), 1):
                if q.lower() in line.lower():
                    out.append({"file": str(p.relative_to(self.root)), "line": i, "text": line[:500]})
                    break
        return {"success": True, "results": out}

    def read_file(self, path: str, max_chars: int = 30000):
        p = self._safe(path)
        if not p.is_file():
            return {"success": False, "error": f"File not found: {path}"}
        return {"success": True, "path": str(p.relative_to(self.root)), "content": p.read_text(encoding="utf-8", errors="ignore")[:max_chars]}

    def write_file(self, path: str, content: str):
        p = self._safe(path)
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(str(content), encoding="utf-8")
        return {"success": True, "path": str(p.relative_to(self.root))}

    def apply_patch(self, path: str, old: str, new: str, replace_all: bool = False):
        p = self._safe(path)
        text = p.read_text(encoding="utf-8", errors="ignore")
        if old not in text:
            return {"success": False, "error": "Exact old text was not found", "path": str(p.relative_to(self.root))}
        count = text.count(old)
        if count > 1 and not replace_all:
            return {"success": False, "error": f"Patch text matches {count} places; set replace_all=true to continue"}
        updated = text.replace(old, new, -1 if replace_all else 1)
        p.write_text(updated, encoding="utf-8")
        return {"success": True, "path": str(p.relative_to(self.root)), "replacements": count if replace_all else 1}

    def diff(self, path: str, old: str, new: str):
        diff = difflib.unified_diff(old.splitlines(), new.splitlines(), lineterm="")
        return {"success": True, "diff": "\n".join(diff)}

    def run_tests(self, target: str = ""):
        target = target.strip()
        candidates = []
        if target:
            candidates = [target]
        else:
            if (self.root / "pytest.ini").exists() or any(self.root.glob("tests/test_*.py")):
                candidates = ["-m", "pytest"]
            elif (self.root / "pyproject.toml").exists():
                candidates = ["-m", "pytest"]
        if not candidates:
            compile_out = subprocess.run(
                ["python", "-m", "compileall", "-q", str(self.root)],
                cwd=self.root,
                capture_output=True,
                text=True,
            )
            return {"success": compile_out.returncode == 0, "command": "python -m compileall -q .", "stdout": compile_out.stdout[-8000:], "stderr": compile_out.stderr[-8000:]}
        cmd = ["python", *candidates]
        proc = subprocess.run(cmd, cwd=self.root, capture_output=True, text=True, timeout=300)
        return {"success": proc.returncode == 0, "command": " ".join(cmd), "returncode": proc.returncode, "stdout": proc.stdout[-12000:], "stderr": proc.stderr[-12000:]}
