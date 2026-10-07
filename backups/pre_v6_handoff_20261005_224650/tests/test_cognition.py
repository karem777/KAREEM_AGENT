from brain.goal_understanding import GoalUnderstanding
from brain.page_perception import PagePerception
from brain.state_reasoner import StateReasoner


class DummyBrain:
    def ask(self, prompt):
        return '{"goal_type":"web_research","site":"noon","country":"Saudi Arabia","currency":"SAR","query":"laptop RTX 4060","constraints":{"max_price":4000},"result_count":5,"required_fields":["name","price","url"],"requires_search":true,"requires_data_collection":true,"verification":["5 eligible results"]}'


def test_goal_understanding_separates_query_and_constraints():
    g = GoalUnderstanding(brain=DummyBrain()).understand(
        "افتح نون وابحث عن لابتوب RTX 4060 بسعر أقل من 4000 ريال سعودي واعرضلي أول 5 نتائج بالاسم والسعر والرابط"
    )
    assert g["site"] == "noon"
    assert g["currency"] == "SAR"
    assert g["constraints"]["max_price"] == 4000
    assert g["result_count"] == 5
    assert "4000" not in (g["query"] or "")


def test_page_perception_detects_search_results_and_currency():
    snap = '''RootWebArea "Search" url="https://shop.example/search?q=RTX"
uid=1_0 search
uid=1_1 combobox "Search" value="RTX"
uid=1_2 link "Laptop RTX 4060 3999 SAR" url="https://shop.example/p1"
uid=1_3 link "Other item 4500 SAR" url="https://shop.example/p2"
'''
    p = PagePerception(brain=DummyBrain()).perceive(snap, {})
    assert p["page_type"] == "search_results"
    assert p["search_fields"]
    assert p["result_links"]
    assert p["currency"] == "SAR"


def test_state_reasoner_proof_requires_eligible_count():
    goal = {
        "currency": "SAR",
        "query": "RTX 4060",
        "result_count": 2,
        "requires_data_collection": True,
        "constraints": {"max_price": 4000},
    }
    page = {
        "url": "https://example.sa/search",
        "page_type": "search_results",
        "country": "Saudi Arabia",
        "currency": "SAR",
        "llm": {
            "candidates": [
                {"name": "Laptop RTX 4060", "price": 3500, "currency": "SAR", "url": "https://example.sa/p1", "evidence": ""},
                {"name": "Laptop RTX 4060", "price": 3900, "currency": "SAR", "url": "https://example.sa/p2", "evidence": ""},
            ]
        },
        "fingerprint": "abc",
    }
    s = StateReasoner().reason(goal, page, [])
    assert s["complete"] is True
    assert s["candidate_count"] == 2
