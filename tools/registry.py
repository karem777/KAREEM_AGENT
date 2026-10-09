from __future__ import annotations

from brain.memory import Memory
from tools.filesystem import FileSystemTool
from tools.memory import MemoryTool
from tools.web import WebTool
from tools.system import SystemTool
from tools.browser import BrowserTool
from tools.desktop import DesktopTool
from tools.learning import LearningTool
from tools.knowledge import KnowledgeTool
from tools.engineering import EngineeringTool
from tools.repair import RepairTool
from tools.security import SecurityTool


class ToolRegistry:
    """Universal capability registry: web, desktop, learning, coding, repair, diagnostics."""

    def __init__(self, workspace):
        self.workspace = workspace
        self.tools = {}
        self.memory = Memory()
        self.register(FileSystemTool(workspace))
        self.register(MemoryTool())
        self.register(WebTool())
        self.register(SystemTool())
        browser = BrowserTool()
        self.register(browser)
        self.register(DesktopTool())
        self.register(LearningTool(browser=browser))
        self.register(KnowledgeTool())
        self.register(EngineeringTool(workspace))
        self.register(RepairTool(workspace))
        self.register(SecurityTool())

    def register(self, tool):
        self.tools[tool.name] = tool

    def get(self, name):
        return self.tools.get(name)

    def validate_call(self, tool_name, action_name, arguments):
        """Validate a proposed call against the registered tool's public schema."""
        if not isinstance(arguments, dict):
            raise ValueError("arguments must be a JSON object")

        tool = self.get(tool_name)
        if tool is None:
            raise ValueError(f"unknown tool: {tool_name}")

        description = tool.describe()
        actions = description.get("actions", {}) if isinstance(description, dict) else {}
        action = actions.get(action_name)
        if not isinstance(action, dict):
            raise ValueError(
                f"unknown action {tool_name}.{action_name}; "
                f"available actions: {', '.join(sorted(actions))}"
            )

        parameters = action.get("parameters", {}) or {}
        unknown = sorted(set(arguments) - set(parameters))
        if unknown:
            raise ValueError(f"unexpected arguments for {tool_name}.{action_name}: {unknown}")

        missing = sorted(
            name for name, spec in parameters.items()
            if isinstance(spec, dict)
            and spec.get("required", False)
            and (name not in arguments or arguments[name] is None)
        )
        if missing:
            raise ValueError(f"missing required arguments for {tool_name}.{action_name}: {missing}")

        expected_types = {
            "string": str,
            "integer": int,
            "number": (int, float),
            "boolean": bool,
            "object": dict,
            "array": list,
        }
        for name, value in arguments.items():
            spec = parameters.get(name) or {}
            expected = expected_types.get(str(spec.get("type", "")).lower())
            if expected is None or value is None:
                continue
            # bool subclasses int in Python, but is not a valid integer argument.
            if expected is int and isinstance(value, bool):
                raise ValueError(f"argument {name!r} must be integer, not boolean")
            if not isinstance(value, expected):
                type_name = spec.get("type", "valid value")
                raise ValueError(f"argument {name!r} must be {type_name}")
        return True

    def describe(self):
        return {name: tool.describe() for name, tool in self.tools.items()}
