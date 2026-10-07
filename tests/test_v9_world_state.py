from brain.page_perception import PagePerception
from brain.state_reasoner import StateReasoner


class DummyBrain:
    def ask(self, prompt):
        return '{"goal_relevance":1.0,"state":"useful","candidates":[]}'


def test_openai_home_is_not_classified_as_search_home_just_because_it_contains_search_button_text():
    snapshot = r'''uid=16_0 RootWebArea "OpenAI | Research & Deployment" url="https://openai.com/"
  uid=16_5 button "Open Search"
  uid=16_73 textbox "Message ChatGPT Quiz me on vocabulary"
  uid=16_79 link "Research" url="https://openai.com/research/"

'''
    page = PagePerception(brain=DummyBrain()).perceive(snapshot, {"site": "google", "query": "OpenAI", "requires_first_result": True})
    assert page["page_type"] != "search_home"


def test_first_result_completion_is_proof_gated_by_successful_click_destination():
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
        "page_type": "search_home",
        "llm": {},
        "result_links": [{"name": "OpenAI Home", "url": "https://openai.com/"}],
        "fingerprint": "openai",
    }
    history = [{
        "role": "tool",
        "tool": "browser",
        "action": "click",
        "arguments": {"first_result": True},
        "result": {"success": True, "clicked_url": "https://openai.com/", "actual_url": "https://openai.com/"},
    }]
    state = StateReasoner().reason(goal, page, history)
    assert state["complete"] is True
    assert state["completion_proof"]["type"] == "first_result_navigation"


def test_first_result_does_not_complete_when_click_destination_differs_from_current_page():
    goal = {
        "site": "google",
        "query": "OpenAI",
        "requires_search": True,
        "requires_first_result": True,
        "result_count": 1,
    }
    page = {
        "url": "https://www.google.com/search?q=OpenAI",
        "page_type": "search_results",
        "result_links": [{"name": "OpenAI", "url": "https://openai.com/"}],
        "fingerprint": "results",
    }
    history = [{
        "role": "tool",
        "tool": "browser",
        "action": "click",
        "arguments": {"first_result": True},
        "result": {"success": True, "clicked_url": "https://openai.com/", "actual_url": "https://openai.com/"},
    }]
    state = StateReasoner().reason(goal, page, history)
    assert state["complete"] is False
    assert state["status"] == "results_ready"
