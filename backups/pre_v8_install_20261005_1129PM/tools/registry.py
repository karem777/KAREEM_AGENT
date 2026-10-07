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

    def describe(self):
        return {name: tool.describe() for name, tool in self.tools.items()}
