
from __future__ import annotations
from tools.windows_operator import WindowsOperator


class LocalComputerTool(WindowsOperator):
    """Compatibility wrapper for the professional Windows operator."""

    def __init__(self, workspace=None):
        super().__init__(workspace=workspace)
        self.name = "computer"

