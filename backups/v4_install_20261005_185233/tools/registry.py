from brain.memory import Memory
from tools.filesystem import FileSystemTool
from tools.memory import MemoryTool
from tools.web import WebTool
from tools.system import SystemTool
from tools.browser import BrowserTool
from tools.desktop import DesktopTool


class ToolRegistry:
    """Central capability registry for web + Windows computer use."""

    def __init__(self, workspace):
        self.tools = {}
        self.memory = Memory()
        self.register(FileSystemTool(workspace))
        self.register(MemoryTool())
        self.register(WebTool())
        self.register(SystemTool())
        self.register(BrowserTool())
        self.register(DesktopTool())

    def register(self, tool):
        self.tools[tool.name] = tool

    def get(self, name):
        return self.tools.get(name)

    def describe(self):
        return {name: tool.describe() for name, tool in self.tools.items()}
