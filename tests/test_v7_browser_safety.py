from brain.page_perception import PagePerception
from brain.state_reasoner import StateReasoner
from brain.planner import Planner
from tools.browser import BrowserTool


def test_agent_ui_is_never_search_home():
    snapshot = '''## Latest page snapshot
uid=1_0 RootWebArea "KAREEM AGENT" url="http://127.0.0.1:5000/"
  uid=1_1 textbox "اكتب رسالتك هنا..."
  uid=1_2 button "➤"
'''
    class DummyBrain:
        def ask(self, prompt):
            return "{}"
    page = PagePerception(brain=DummyBrain()).perceive(snapshot, {"site": "noon", "query": "لابتوب"})
    assert page["page_type"] == "agent_control_ui"


def test_agent_ui_becomes_wrong_context_for_external_goal():
    page = {
        "url": "http://127.0.0.1:5000/",
        "page_type": "agent_control_ui",
        "country": None,
        "currency": None,
        "result_links": [],
        "llm": {},
    }
    goal = {"site": "noon", "country": "Saudi Arabia", "currency": "SAR", "query": "لابتوب"}
    state = StateReasoner().reason(goal, page, [])
    assert state["status"] == "wrong_context"
    assert "agent_control_ui:external_target_required" in state["mismatches"]


def test_failed_open_does_not_count_as_opened():
    history = [{
        "role": "tool", "tool": "browser", "action": "open_url",
        "arguments": {"url": "https://www.noon.com/saudi-en/"},
        "result": {"success": False},
    }]
    assert Planner._same_url_already_opened(history, "https://www.noon.com/saudi-en/") is False


def test_browser_helper_recognizes_agent_ui():
    assert BrowserTool._is_agent_ui_url("http://127.0.0.1:5000/") is True
    assert BrowserTool._is_agent_ui_url("http://localhost:5000/") is True
    assert BrowserTool._is_agent_ui_url("https://www.google.com/") is False


def test_browser_origin_normalization():
    assert BrowserTool._origin("HTTPS://WWW.GOOGLE.COM/path?q=x") == "https://www.google.com"
