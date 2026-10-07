from brain.goal_understanding import GoalUnderstanding
from brain.state_reasoner import StateReasoner
from core.cognition import CognitiveRuntime


class DummyBrain:
    def ask(self, prompt):
        if "Goal Understanding" in prompt:
            return '{"goal_type":"web_research","site":"google","query":"OpenAI وافتح أول نتيجة","requires_search":true,"requires_first_result":true,"result_count":1}'
        return '{"goal_relevance":0.9,"state":"useful","candidates":[]}'


def test_open_first_result_is_action_goal_not_collection_goal():
    g = GoalUnderstanding(brain=DummyBrain()).understand(
        "افتح جوجل وابحث عن OpenAI وافتح أول نتيجة"
    )
    assert g["requires_first_result"] is True
    assert g["requires_data_collection"] is False
    assert g["query"] == "OpenAI"


def test_first_result_is_not_complete_on_search_results_even_with_candidate():
    goal = {
        "site": "google",
        "query": "OpenAI",
        "requires_search": True,
        "requires_first_result": True,
        "result_count": 1,
        "requires_data_collection": False,
    }
    page = {
        "url": "https://www.google.com/search?q=OpenAI",
        "page_type": "search_results",
        "llm": {"candidates": [
            {"name": "OpenAI", "url": "https://openai.com/", "evidence": "OpenAI"}
        ]},
        "result_links": [
            {"name": "OpenAI", "url": "https://openai.com/"}
        ],
        "fingerprint": "results",
    }
    s = StateReasoner().reason(goal, page, [])
    assert s["complete"] is False
    assert s["status"] == "results_ready"


def test_first_result_completes_after_successful_click_and_navigation():
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
        "llm": {"candidates": []},
        "result_links": [],
        "fingerprint": "detail",
    }
    history = [
        {"role": "tool", "tool": "browser", "action": "click", "arguments": {"first_result": True}, "result": {"success": True}}
    ]
    s = StateReasoner().reason(goal, page, history)
    assert s["complete"] is True
    assert s["status"] == "complete"


def test_cognition_hints_click_first_result_after_search():
    rt = CognitiveRuntime(brain=DummyBrain())
    rt.goal = {
        "site": "google",
        "query": "OpenAI",
        "requires_search": True,
        "requires_first_result": True,
        "result_count": 1,
        "requires_data_collection": False,
    }
    rt.page = {
        "url": "https://www.google.com/search?q=OpenAI",
        "page_type": "search_results",
        "result_links": [{"name": "OpenAI", "url": "https://openai.com/"}],
        "fingerprint": "results",
    }
    rt.state = {"status": "results_ready", "complete": False}
    hints = rt.candidate_action_hints([])
    assert hints[0]["tool"] == "browser"
    assert hints[0]["action"] == "click"
    assert hints[0]["arguments"]["first_result"] is True
