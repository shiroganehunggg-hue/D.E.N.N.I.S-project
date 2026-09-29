import logging
import time
from typing import Any, Dict, Tuple

import win32api
import win32con
import win32clipboard
import win32gui

from src.tools.base import Tool

logger = logging.getLogger(__name__)

KEY_TO_VK = {
    "enter": 13,
    "ctrl": 17,
    "alt": 18,
    "shift": 16,
    "escape": 27,
    "tab": 9,
    "space": 32,
    "left": 37,
    "right": 39,
    "up": 38,
    "down": 40,
    "a": 65,
    "b": 66,
    "c": 67,
    "d": 68,
    "e": 69,
    "f": 70,
    "g": 71,
    "h": 72,
    "i": 73,
    "j": 74,
    "k": 75,
    "l": 76,
    "m": 77,
    "n": 78,
    "o": 79,
    "p": 80,
    "q": 81,
    "r": 82,
    "s": 83,
    "t": 84,
    "u": 85,
    "v": 86,
    "w": 87,
    "x": 88,
    "y": 89,
    "z": 90,
}


def _key_to_vk(key: str) -> int:
    key_lower = str(key).strip().lower()
    if key_lower not in KEY_TO_VK:
        raise ValueError(f"Phím không được hỗ trợ: {key}")
    return KEY_TO_VK[key_lower]


class PressKeyTool(Tool):
    """Press a single key on the keyboard."""

    name = "press_key"
    description = "Nhấn một phím đơn lẻ trên bàn phím"

    def run(self, key: str) -> dict:
        try:
            vk = _key_to_vk(key)
            win32api.keybd_event(vk, 0, 0, 0)
            win32api.keybd_event(vk, 0, win32con.KEYEVENTF_KEYUP, 0)
            return {"success": True, "key": key}
        except Exception as exc:
            logger.exception("Failed to press key: %s", exc)
            return {"success": False, "error": str(exc)}

    def schema(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "description": self.description,
            "parameters": {"type": "object", "properties": {"key": {"type": "string", "description": "Tên phím như enter, ctrl, a"}}, "required": ["key"]},
        }

class HotkeyTool(Tool):
    """Send a keyboard shortcut combining multiple keys."""

    name = "hotkey"
    description = "Gửi tổ hợp phím như Ctrl+C hoặc Alt+Tab"

    def run(self, **kwargs) -> dict:
        try:
            keys = kwargs.get("keys")
            if not keys:
                raise ValueError("Cần ít nhất một phím")
            if isinstance(keys, str):
                keys = [keys]
            vk_codes = [_key_to_vk(key) for key in keys]
            for vk in vk_codes:
                win32api.keybd_event(vk, 0, 0, 0)
            for vk in reversed(vk_codes):
                win32api.keybd_event(vk, 0, win32con.KEYEVENTF_KEYUP, 0)
            return {"success": True, "keys": list(keys)}
        except Exception as exc:
            logger.exception("Failed to send hotkey: %s", exc)
            return {"success": False, "error": str(exc)}

    def schema(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "description": self.description,
            "parameters": {
                "type": "object",
                "properties": {
                    "keys": {"type": "array", "items": {"type": "string"}, "description": "Danh sách phím như ctrl, c"}
                },
                "required": ["keys"],
            },
        }


class TypeTextTool(Tool):
    """Type a text string into the active window."""

    name = "type_text"
    description = "Gõ một chuỗi văn bản vào cửa sổ đang active"

    def run(self, text: str) -> str:
        try:
            if not text:
                raise ValueError("text không được rỗng")

            foreground = win32gui.GetForegroundWindow()
            focus = win32gui.GetFocus()
            if not foreground and not focus:
                return {"success": False, "error": "Không có cửa sổ active để nhập", "data": {"text": text}}

            win32clipboard.OpenClipboard()
            try:
                win32clipboard.EmptyClipboard()
                win32clipboard.SetClipboardText(str(text), win32clipboard.CF_UNICODETEXT)
            finally:
                win32clipboard.CloseClipboard()

            win32api.keybd_event(0x11, 0, 0, 0)
            win32api.keybd_event(0x56, 0, 0, 0)
            win32api.keybd_event(0x56, 0, win32con.KEYEVENTF_KEYUP, 0)
            win32api.keybd_event(0x11, 0, win32con.KEYEVENTF_KEYUP, 0)
            time.sleep(0.1)
            return {"success": True, "result": f"Đã nhập: {text}", "data": {"text": text}}
        except Exception as exc:
            logger.exception("Failed to type text: %s", exc)
            return {"success": False, "error": str(exc), "data": {"text": text}}

    def schema(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "description": self.description,
            "parameters": {"type": "object", "properties": {"text": {"type": "string", "description": "Chuỗi văn bản cần nhập"}}, "required": ["text"]},
        }
