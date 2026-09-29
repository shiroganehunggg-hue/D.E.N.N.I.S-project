import logging
from typing import Any, Dict

import win32clipboard

from src.tools.base import Tool

logger = logging.getLogger(__name__)


class CopyTool(Tool):
    """Copy a string to the Windows clipboard."""

    name = "copy"
    description = "Sao chép văn bản vào clipboard"

    def run(self, text: str) -> dict:
        try:
            if text is None:
                raise ValueError("text không được None")
            win32clipboard.OpenClipboard()
            try:
                win32clipboard.EmptyClipboard()
                win32clipboard.SetClipboardText(str(text))
            finally:
                win32clipboard.CloseClipboard()
            return {"success": True, "text": text}
        except Exception as exc:
            logger.exception("Failed to copy text: %s", exc)
            return {"success": False, "error": str(exc)}

    def schema(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "description": self.description,
            "parameters": {"type": "object", "properties": {"text": {"type": "string", "description": "Văn bản cần sao chép"}}, "required": ["text"]},
        }


class PasteTool(Tool):
    """Paste the current clipboard contents into the active application."""

    name = "paste"
    description = "Dán nội dung hiện có trong clipboard"

    def run(self) -> dict:
        try:
            win32clipboard.OpenClipboard()
            try:
                text = win32clipboard.GetClipboardData()
            finally:
                win32clipboard.CloseClipboard()
            return {"success": True, "text": text}
        except Exception as exc:
            logger.exception("Failed to paste clipboard: %s", exc)
            return {"success": False, "error": str(exc)}

    def schema(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "description": self.description,
            "parameters": {"type": "object", "properties": {}, "required": []},
        }
