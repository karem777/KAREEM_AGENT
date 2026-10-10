from core.tool_router import ToolRouter


def test_powershell_task_keeps_windows_and_research_tools_available():
    available = {
        "computer": {}, "windows": {}, "filesystem": {}, "developer": {},
        "web": {}, "browser": {}, "learning": {}, "knowledge": {},
        "memory": {}, "experience": {}, "research": {},
    }
    selected = ToolRouter().select("Run this in PowerShell and fix the error", available)
    assert {"windows", "computer", "web", "browser", "learning", "knowledge"} <= selected


def test_vscode_task_keeps_developer_and_computer_tools():
    available = {
        "computer": {}, "windows": {}, "filesystem": {}, "developer": {},
        "web": {}, "browser": {}, "learning": {}, "knowledge": {},
        "memory": {}, "experience": {}, "research": {},
    }
    selected = ToolRouter().select("Open VS Code and edit the project", available)
    assert {"developer", "computer", "web", "browser", "learning"} <= selected
