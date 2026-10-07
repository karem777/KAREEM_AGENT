from brain.planner import Planner


class FakeGoalState:
    def __init__(self):
        self.steps = [
            {"id": "s1", "tool": "browser", "action": "open_url", "arguments": {"url": "https://www.google.com"}, "depends_on": [], "required": True, "status": "done"},
            {"id": "s2", "tool": "browser", "action": "open_url", "arguments": {"url": "https://www.google.com/search?q=OpenAI"}, "depends_on": ["s1"], "required": True, "status": "done"},
            {"id": "s3", "tool": "browser", "action": "inspect", "arguments": {}, "depends_on": ["s2"], "required": True, "status": "done"},
            {"id": "s4", "tool": "browser", "action": "click", "arguments": {}, "depends_on": ["s3"], "required": True, "status": "pending"},
        ]


def test_goal_state_wins_over_llm_drift():
    class Brain:
        def ask(self, _):
            return '{"type":"tool_calls","calls":[{"tool":"web","action":"search","arguments":{"query":"OpenAI"}}]}'

    planner = Planner(brain=Brain())
    result = planner.plan(
        "افتح جوجل وابحث عن OpenAI وافتح أول نتيجة",
        analysis={"mode": "execute"},
        goal_state=FakeGoalState(),
    )
    assert result["type"] == "tool_calls"
    assert result["calls"][0]["tool"] == "browser"
    assert result["calls"][0]["action"] == "click"
