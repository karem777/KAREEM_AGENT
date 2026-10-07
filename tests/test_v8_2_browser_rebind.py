from brain.state_reasoner import StateReasoner
from tools.browser import BrowserTool


def test_click_rebases_expected_origin_after_navigation():
    browser = BrowserTool()
    browser._bound_page_id = 3
    browser._expected_origin = "https://www.google.com"
    browser._pending_target_url = None

    def fake_guard(page_id, require_expected=True):
        return None

    def fake_call(name, arguments=None):
        if name == "select_page":
            return {"success": True, "text": ""}
        if name == "take_snapshot":
            return {"success": True, "text": 'uid=1_0 RootWebArea "Google" url="https://www.google.com/search?q=OpenAI"'}
        if name == "click":
            return {
                "success": True,
                "text": 'uid=28_0 RootWebArea "OpenAI" url="https://openai.com/"',
            }
        raise AssertionError(name)

    browser._guard_bound_page = fake_guard
    browser._call = fake_call

    result = browser.click(page_id=3, uid="23_36", first_result=True)

    assert result["success"] is True
    assert result["actual_url"] == "https://openai.com/"
    assert browser._expected_origin == "https://openai.com"
    assert browser._pending_target_url is None


def test_first_result_completes_after_successful_click_even_when_click_result_has_same_origin_redirect():
    goal = {
        "site": "google",
        "query": "OpenAI",
        "requires_search": True,
        "requires_first_result": True,
        "result_count": 1,
        "requires_data_collection": False,
    }
    page = {
        "url": "https://openai.com/",
        "page_type": "detail",
        "llm": {},
        "result_links": [],
        "fingerprint": "detail",
    }
    history = [{
        "role": "tool",
        "tool": "browser",
        "action": "click",
        "arguments": {"first_result": True},
        "result": {
            "success": True,
            "clicked_url": "https://openai.com/",
            "actual_url": "https://openai.com/",
        },
    }]
    state = StateReasoner().reason(goal, page, history)
    assert state["complete"] is True
    assert state["status"] == "complete"


def test_drift_guard_still_rejects_unexpected_external_page_before_action():
    browser = BrowserTool()
    browser._bound_page_id = 3
    browser._expected_origin = "https://www.google.com"
    browser._page_snapshot = lambda page_id, verbose=False: 'uid=1_0 RootWebArea "Other" url="https://example.com/"'
    try:
        browser._guard_bound_page(3, require_expected=True)
    except RuntimeError as exc:
        assert "expected https://www.google.com, got https://example.com" in str(exc)
    else:
        raise AssertionError("drift guard failed open")
