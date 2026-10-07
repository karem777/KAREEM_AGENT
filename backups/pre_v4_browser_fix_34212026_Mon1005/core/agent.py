from pathlib import Path

from core.config import load_config
from core.logger import logger
from tools.registry import ToolRegistry
from tools.executor import ToolExecutor


class Agent:
    def __init__(self):
        self.config = load_config()
        self.name = self.config["agent_name"]

        root = Path(__file__).resolve().parent.parent
        workspace = root / self.config["workspace"]

        self.tools = ToolRegistry(workspace)
        self.executor = ToolExecutor(self.tools)

        logger.info("Agent initialized: %s", self.name)
        logger.info(
            "Tools loaded: %s",
            list(self.tools.tools.keys())
        )

    def status(self):
        return {
            "name": self.name,
            "version": self.config["version"],
            "status": "online",
            "tools": list(self.tools.tools.keys())
        }

    def run(self, instruction):
        logger.info(
            "Instruction received: %s",
            instruction
        )

        return {
            "success": True,
            "instruction": instruction,
            "message": "Instruction received by Agent Core."
        }

    def execute_tool(self, tool_name, action, **kwargs):
        logger.info(
            "Executing tool=%s action=%s",
            tool_name,
            action
        )

        return self.executor.execute(
            tool_name,
            action,
            **kwargs
        )
