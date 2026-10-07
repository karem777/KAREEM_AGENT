from __future__ import annotations

import inspect
import re
from typing import Any


class ToolExecutorV4:
    def __init__(self, registry):
        self.registry = registry

    def execute(self, tool_name: str, action: str, **kwargs: Any) -> dict[str, Any]:
        tool = self.registry.get(tool_name)
        if tool is None:
            return {"success": False, "error": f"Tool not found: {tool_name}"}
        fn = getattr(tool, action, None)
        if not callable(fn):
            actions = []
            try:
                actions = list((tool.describe() or {}).get("actions", {}).keys())
            except Exception:
                pass
            return {"success": False, "error": f"Action not found: {tool_name}.{action}", "available_actions": actions}
        try:
            sig = inspect.signature(fn)
            params = sig.parameters
            if any(p.kind == inspect.Parameter.VAR_KEYWORD for p in params.values()):
                accepted = dict(kwargs)
            else:
                allowed = {k for k, p in params.items() if k != "self" and p.kind in (inspect.Parameter.POSITIONAL_OR_KEYWORD, inspect.Parameter.KEYWORD_ONLY)}
                accepted = {k: v for k, v in kwargs.items() if k in allowed}
            out = fn(**accepted)
            if isinstance(out, dict):
                return out
            return {"success": True, "result": out}
        except TypeError as exc:
            missing = re.search(r"missing .* required positional argument[s]?: '([^']+)'", str(exc))
            return {"success": False, "error": str(exc), "missing_argument": missing.group(1) if missing else None}
        except Exception as exc:
            return {"success": False, "error": f"{type(exc).__name__}: {exc}"}
