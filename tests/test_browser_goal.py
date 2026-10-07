from core.browser_goal import BrowserGoalController


def test_search_first_result_sequence():
    c = BrowserGoalController()
    goal = "افتح جوجل وابحث عن OpenAI وافتح أول نتيجة"

    assert c.next_action(goal, []) == {
        "tool": "browser", "action": "open_url", "arguments": {"url": "https://www.google.com"}
    }

    history = [{"role": "user", "content": goal}, {
        "role": "tool", "tool": "browser", "action": "open_url",
        "arguments": {"url": "https://www.google.com"},
        "result": {"success": True, "url": "https://www.google.com", "page_id": 1, "text": "Google"},
    }]
    assert c.next_action(goal, history)["action"] == "inspect"

    history.append({"role": "tool", "tool": "browser", "action": "inspect", "arguments": {},
                    "result": {"success": True, "url": "https://www.google.com", "text": 'RootWebArea "Google" textbox "بحث"'}})
    step = c.next_action(goal, history)
    assert step["action"] == "fill"
    assert step["arguments"]["value"] == "OpenAI"

    history.append({"role": "tool", "tool": "browser", "action": "fill", "arguments": step["arguments"],
                    "result": {"success": True, "url": "https://www.google.com", "text": 'textbox "بحث" value="OpenAI"'}})
    assert c.next_action(goal, history)["arguments"]["key"] == "Enter"

    history.append({"role": "tool", "tool": "browser", "action": "press_key", "arguments": {"key": "Enter"},
                    "result": {"success": True, "url": "https://www.google.com/search?q=OpenAI", "text": "Search results"}})
    assert c.next_action(goal, history)["action"] == "inspect"

    history.append({"role": "tool", "tool": "browser", "action": "inspect", "arguments": {},
                    "result": {"success": True, "url": "https://www.google.com/search?q=OpenAI", "text": 'heading "Search results"'}})
    assert c.next_action(goal, history) == {
        "tool": "browser", "action": "click", "arguments": {"first_result": True}
    }

    history.append({"role": "tool", "tool": "browser", "action": "click", "arguments": {"first_result": True},
                    "result": {"success": True, "url": "https://openai.com/"}})
    assert c.next_action(goal, history)["action"] == "inspect"


def test_inspect_snapshot_url_drives_click_without_refill_loop():
    c = BrowserGoalController()
    goal = "افتح جوجل وابحث عن OpenAI وافتح أول نتيجة"
    history = [
        {"role": "user", "content": goal},
        {"role": "tool", "tool": "browser", "action": "press_key", "arguments": {"key": "Enter"},
         "result": {"success": True, "page_id": 1, "text": "Successfully pressed key: Enter"}},
        {"role": "tool", "tool": "browser", "action": "inspect", "arguments": {},
         "result": {
             "success": True,
             "page_id": 1,
             "snapshot": 'RootWebArea "OpenAI - بحث Google" url="https://www.google.com/search?q=OpenAI"',
         }},
    ]
    assert c.next_action(goal, history) == {
        "tool": "browser", "action": "click", "arguments": {"first_result": True}
    }
