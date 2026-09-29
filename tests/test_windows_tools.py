from unittest.mock import call, patch

import win32con

from src.tools.registry import discover_tools
from src.tools.windows.keyboard import HotkeyTool


def test_windows_tools_are_discovered():
    tools = discover_tools()
    names = {tool.name for tool in tools}

    assert "launch_app" in names
    assert "list_windows" in names
    assert "move_mouse" in names
    assert "press_key" in names
    assert "copy" in names
    assert "take_screenshot" in names
    assert "run_python" not in names


def test_hotkey_tool_presses_keys_and_releases_in_reverse_order():
    with patch("src.tools.windows.keyboard.win32api.keybd_event") as keybd_event:
        result = HotkeyTool().run(keys=["ctrl", "shift", "p"])

    assert result["success"] is True
    assert keybd_event.call_args_list == [
        call(17, 0, 0, 0),
        call(16, 0, 0, 0),
        call(80, 0, 0, 0),
        call(80, 0, win32con.KEYEVENTF_KEYUP, 0),
        call(16, 0, win32con.KEYEVENTF_KEYUP, 0),
        call(17, 0, win32con.KEYEVENTF_KEYUP, 0),
    ]
