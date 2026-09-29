import logging
from typing import Any, Dict

import win32gui
from PIL import ImageGrab

from src.tools.base import Tool

logger = logging.getLogger(__name__)


class TakeScreenshotTool(Tool):
    """Capture the entire screen as an image."""

    name = "take_screenshot"
    description = "Chụp toàn bộ màn hình"

    def run(self) -> dict:
        try:
            image = ImageGrab.grab()
            return {"success": True, "size": image.size, "mode": image.mode}
        except Exception as exc:
            logger.exception("Failed to take screenshot: %s", exc)
            return {"success": False, "error": str(exc)}

    def schema(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "description": self.description,
            "parameters": {"type": "object", "properties": {}, "required": []},
        }


class CaptureWindowTool(Tool):
    """Capture a specific window by title."""

    name = "capture_window"
    description = "Chụp ảnh một cửa sổ cụ thể"

    def run(self, title: str) -> dict:
        try:
            if not title or not str(title).strip():
                raise ValueError("title không được rỗng")
            target = str(title).strip().lower()
            hwnd = None
            def enum_handler(handle, _):
                nonlocal hwnd
                if hwnd is not None:
                    return
                if win32gui.IsWindowVisible(handle):
                    current_title = win32gui.GetWindowText(handle)
                    if target in current_title.lower():
                        hwnd = handle
            win32gui.EnumWindows(enum_handler, None)
            if hwnd is None:
                return {"success": False, "error": f"Không tìm thấy cửa sổ: {title}"}
            left, top, right, bottom = win32gui.GetWindowRect(hwnd)
            image = ImageGrab.grab(bbox=(left, top, right, bottom))
            return {"success": True, "title": title, "size": image.size, "mode": image.mode}
        except Exception as exc:
            logger.exception("Failed to capture window: %s", exc)
            return {"success": False, "error": str(exc)}

    def schema(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "description": self.description,
            "parameters": {"type": "object", "properties": {"title": {"type": "string", "description": "Tiêu đề cửa sổ cần chụp"}}, "required": ["title"]},
        }
