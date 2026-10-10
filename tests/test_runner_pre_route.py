from core.runner import AgentRunner


def test_pre_route_folder_creation_is_deterministic():
    call = AgentRunner._pre_route("اعمل مجلد باسم cnc")

    assert call == {
        "tool": "filesystem",
        "action": "create_directory",
        "arguments": {"path": "cnc"},
    }


def test_pre_route_desktop_folder_creation_keeps_desktop_alias():
    call = AgentRunner._pre_route("اعمل مجلد على الديسكتوب باسم cnc")

    assert call == {
        "tool": "filesystem",
        "action": "create_directory",
        "arguments": {"path": "Desktop/cnc"},
    }


def test_pre_route_launches_only_allowlisted_apps():
    call = AgentRunner._pre_route("افتح كروم")

    assert call == {
        "tool": "desktop",
        "action": "open_app",
        "arguments": {"command": "chrome"},
    }
    assert AgentRunner._pre_route("افتح برنامج غير معروف") is None


def test_pre_route_does_not_guess_ambiguous_folder_names():
    assert AgentRunner._pre_route("اعمل مجلد ../outside") is None
