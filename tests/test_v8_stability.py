from brain.goal_understanding import GoalUnderstanding
from brain.planner import Planner


class Brain:
    def ask(self, prompt):
        if "Goal Understanding" in prompt:
            return '{"goal_type":"web_research","site":"google","query":"OpenAI وافتح","requires_search":true,"requires_first_result":true,"result_count":1}'
        return '{}'


def test_google_goal_gets_canonical_start_url_and_clean_query():
    g = GoalUnderstanding(brain=Brain()).understand("افتح جوجل وابحث عن OpenAI وافتح أول نتيجة")
    assert g["site"] == "google"
    assert g["start_url"] == "https://www.google.com/"
    assert g["query"] == "OpenAI"


def test_planner_opens_known_site_directly():
    planner = Planner(brain=Brain())
    cognition = {
        "goal": {"site": "google", "start_url": "https://www.google.com/", "query": "OpenAI"},
        "page": {}, "state": {}, "hints": []
    }
    plan = planner.plan("dummy", history=[], cognition=cognition)
    assert plan["tool"] == "browser"
    assert plan["action"] == "open_url"
    assert plan["arguments"]["url"] == "https://www.google.com/"


def test_unknown_site_search_fails_closed_after_two_failures():
    planner = Planner(brain=Brain())
    cognition = {
        "goal": {"site": "exampleunknown", "query": "x"},
        "page": {}, "state": {}, "hints": []
    }
    history = [
        {"role":"tool","tool":"web","action":"search","arguments":{"query":"exampleunknown official website"},"result":{"success":False}},
        {"role":"tool","tool":"web","action":"search","arguments":{"query":"exampleunknown official website"},"result":{"success":False}},
    ]
    plan = planner.plan("dummy", history=history, cognition=cognition)
    assert plan["type"] == "chat"
    assert plan["content"].startswith("__TASK_FAILED__")
