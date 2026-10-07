from brain.goal_understanding import GoalUnderstanding
from brain.planner import Planner
from brain.state_reasoner import StateReasoner


class Brain:
    def ask(self, prompt):
        if "Goal Understanding" in prompt:
            return '{"goal_type":"web_research","site":"noon","country":"Saudi Arabia","currency":"SAR","query":"laptop RTX 4060","constraints":{"max_price":4000},"result_count":5,"required_fields":["name","price","url"],"requires_search":true,"requires_data_collection":true,"verification":["Saudi","SAR","<4000"]}'
        return '{"goal_relevance":0.9,"state":"useful","candidates":[]}'


def test_goal_query_has_no_constraints_or_country_prefix():
    g = GoalUnderstanding(brain=Brain()).understand(
        "افتح نون السعودية وابحث عن لابتوب RTX 4060 بسعر أقل من 4000 ريال سعودي، واعرض أول 5 نتائج بالاسم والسعر والرابط"
    )
    assert g["query"] == "لابتوب RTX 4060"
    assert "4000" not in g["query"]
    assert "السعودية" not in g["query"]


def test_successful_web_search_hands_off_to_browser():
    planner = Planner(brain=Brain())
    cognition = {
        "goal": {"site": "noon", "country": "Saudi Arabia", "currency": "SAR"},
        "page": {},
        "state": {},
        "hints": [],
    }
    history = [
        {"role": "tool", "tool": "web", "action": "search", "arguments": {"query": "noon official Saudi Arabia website"},
         "result": {"success": True, "results": [
             {"title": "Superior online shopping in Saudi Arabia - noon", "url": "https://www.noon.com/saudi-en/"},
             {"title": "Noon UAE", "url": "https://www.noon.com/uae-en/"},
         ]}}
    ]
    plan = planner.plan("dummy", history=history, cognition=cognition)
    assert plan["tool"] == "browser"
    assert plan["action"] == "open_url"
    assert "saudi-en" in plan["arguments"]["url"]


def test_web_search_is_not_repeated_after_successful_handoff_candidate():
    planner = Planner(brain=Brain())
    cognition = {
        "goal": {"site": "noon", "country": "Saudi Arabia", "currency": "SAR"},
        "page": {},
        "state": {},
        "hints": [],
    }
    history = [
        {"role": "tool", "tool": "web", "action": "search", "arguments": {"query": "noon official Saudi Arabia website"},
         "result": {"success": True, "results": [{"title": "noon Saudi Arabia", "url": "https://www.noon.com/saudi-en/"}]}},
        {"role": "tool", "tool": "browser", "action": "open_url", "arguments": {"url": "https://www.noon.com/saudi-en/"},
         "result": {"success": True, "url": "https://www.noon.com/saudi-en/"}},
    ]
    # With a browser context now present, planner must not fall back to discovery loop.
    plan = planner.plan("dummy", history=history, cognition=cognition)
    assert not (plan.get("tool") == "web" and plan.get("action") == "search")


def test_completion_requires_five_eligible_rows():
    goal = {
        "country": "Saudi Arabia", "currency": "SAR", "query": "laptop RTX 4060",
        "result_count": 5, "requires_data_collection": True,
        "constraints": {"max_price": 4000},
    }
    page = {
        "url": "https://www.noon.com/saudi-en/search?q=RTX",
        "page_type": "search_results", "country": "Saudi Arabia", "currency": "SAR",
        "llm": {"candidates": [
            {"name": f"Laptop RTX 4060 {i}", "price": 3500+i, "currency": "SAR", "url": f"https://noon.com/p{i}", "evidence": "RTX 4060"}
            for i in range(5)
        ]},
        "fingerprint": "abc",
    }
    state = StateReasoner().reason(goal, page, [])
    assert state["complete"] is True
    assert state["candidate_count"] == 5
