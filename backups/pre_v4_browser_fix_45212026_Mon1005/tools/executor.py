from __future__ import annotations

import inspect
import re
from typing import Any


class ToolExecutor:
    """Hard execution boundary with aliasing + signature-aware compatibility."""

    TOOL_ALIASES = {
        "execute_browser_action": "browser",
        "browser_action": "browser",
        "browser_tool": "browser",
        "filesystem_tool": "filesystem",
        "memory_tool": "memory",
        "computer": "desktop",
        "pc": "desktop",
        "windows": "desktop",
        "desktop_tool": "desktop",
    }

    ACTION_ALIASES = {
        "navigate": "open_url",
        "navigate_url": "open_url",
        "open": "open_url",
        "inspect_page": "inspect",
        "inspect_current_page": "inspect",
        "type": "type_text",
        "input_text": "type_text",
        "key": "press_key",
        "backward": "back",
    }

    def __init__(self, registry):
        self.registry = registry

    def execute(self, tool_name: str, action: str, **kwargs):
        original = {"tool": tool_name, "action": action, "arguments": dict(kwargs)}
        tool_name, action = self._normalize_name(tool_name, action)

        tool = self.registry.get(tool_name)
        if tool is None:
            return {"success": False, "error": f"Tool not found: {tool_name}", "call": original}

        method = getattr(tool, action, None)
        if method is None or action.startswith("_"):
            return {"success": False, "error": f"Action not found: {action}", "call": original}

        clean = self._filter_kwargs(method, kwargs)
        dropped = sorted(set(kwargs) - set(clean))

        try:
            result = method(**clean)
            out = result if isinstance(result, dict) else {"success": True, "result": result}
            if "success" not in out:
                out["success"] = True
            out.setdefault("normalized_call", {"tool": tool_name, "action": action, "arguments": clean})
            if dropped:
                out["compatibility"] = {"dropped_arguments": dropped, "reason": "Not accepted by current tool signature"}
            return out
        except TypeError as exc:
            unexpected = self._unexpected_keyword(str(exc))
            if unexpected and unexpected in clean:
                retry = dict(clean)
                retry.pop(unexpected, None)
                try:
                    result = method(**retry)
                    out = result if isinstance(result, dict) else {"success": True, "result": result}
                    if "success" not in out:
                        out["success"] = True
                    out["compatibility"] = {"dropped_arguments": [unexpected], "reason": str(exc)}
                    out["normalized_call"] = {"tool": tool_name, "action": action, "arguments": retry}
                    return out
                except Exception as retry_exc:
                    return {"success": False, "error": f"{type(retry_exc).__name__}: {retry_exc}", "compatibility": {"original_error": str(exc)}}
            return {"success": False, "error": str(exc), "call": original}
        except Exception as exc:
            return {"success": False, "error": f"{type(exc).__name__}: {exc}", "call": original}

    def _filter_kwargs(self, method, kwargs: dict[str, Any]) -> dict[str, Any]:
        try:
            sig = inspect.signature(method)
        except Exception:
            return dict(kwargs)
        params = sig.parameters
        if any(p.kind == inspect.Parameter.VAR_KEYWORD for p in params.values()):
            return dict(kwargs)
        accepted = {name for name, p in params.items() if name != "self" and p.kind in (inspect.Parameter.POSITIONAL_OR_KEYWORD, inspect.Parameter.KEYWORD_ONLY)}
        return {k: v for k, v in kwargs.items() if k in accepted}

    def describe(self):
        return self.registry.describe()

    def _normalize_name(self, tool_name: str, action: str):
        tool = str(tool_name or "").strip().lower()
        act = str(action or "").strip()
        if "." in act and not tool:
            tool, act = act.split(".", 1)
        elif "." in tool and not act:
            tool, act = tool.split(".", 1)
        tool = self.TOOL_ALIASES.get(tool, tool)
        act = self.ACTION_ALIASES.get(act.lower(), act)
        return tool, act

    @staticmethod
    def _unexpected_keyword(message: str) -> str | None:
        match = re.search(r"unexpected keyword argument ['\"]([^'\"]+)", message)
        return match.group(1) if match else None
