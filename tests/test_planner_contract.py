import json

from brain.planner import Planner


class FakeBrain:
    def __init__(self, responses):
        self.responses = list(responses)
        self.prompts = []

    def ask(self, prompt):
        self.prompts.append(prompt)
        return self.responses.pop(0)


def test_planner_repairs_invalid_json_and_validates_decision():
    brain = FakeBrain([
        "not-json",
        '{"type":"tool_call","tool":"filesystem","action":"create_directory","arguments":{"path":"demo"}}',
    ])
    planner = Planner(brain=brain)

    result = planner.plan(
        user_message="Create a folder named demo",
        history=[],
        tools={
            "filesystem": {
                "actions": {
                    "create_directory": {
                        "description": "Create a directory",
                        "parameters": {"path": {"type": "string", "required": True}},
                    }
                }
            }
        },
    )

    assert result == {
        "type": "tool_call",
        "tool": "filesystem",
        "action": "create_directory",
        "arguments": {"path": "demo"},
    }
    assert len(brain.prompts) == 2
    assert "invalid_output" in brain.prompts[1]
    assert "validation_error" in brain.prompts[1]


def test_planner_only_passes_goal_and_latest_tool_result_as_dynamic_context():
    brain = FakeBrain([
        '{"type":"chat","content":"Need more detail."}',
    ])
    planner = Planner(brain=brain)

    planner.plan(
        user_message="Research the basics of CNC machines",
        history=[
            {"role": "assistant", "content": "old conversation secret"},
            {"role": "tool", "tool": "web", "action": "search", "result": {"results": [{"title": "CNC"}]}},
            {"role": "assistant", "content": "old assistant content"},
        ],
        tools={"web": {"actions": {"search": {"parameters": {"query": {"type": "string", "required": True}}}}}},
    )

    prompt = brain.prompts[0]
    assert "Research the basics of CNC machines" in prompt
    assert '"tool":"web"' in prompt
    assert "old conversation secret" not in prompt
    assert "old assistant content" not in prompt


def test_planner_stops_after_two_repair_retries():
    brain = FakeBrain(["oops", "still not json", "also not json"])
    planner = Planner(brain=brain)

    result = planner.plan(
        user_message="Research CNC machines",
        history=[],
        tools={},
    )

    assert result["type"] == "chat"
    assert result["content"].startswith("__TASK_FAILED__")
    assert len(brain.prompts) == 3
