import logging
import time
from typing import Any, Dict, List, Optional, Tuple

import win32api
import win32con

from src.tools.base import Tool

logger = logging.getLogger(__name__)


class MoveMouseTool(Tool):
    """Move the mouse cursor to a given screen coordinate."""

    name = "move_mouse"
    description = "Di chuyển con trỏ chuột tới tọa độ (x, y)"

    def run(self, x: int, y: int) -> dict:
        try:
            win32api.SetCursorPos((int(x), int(y)))
            return {"success": True, "x": int(x), "y": int(y)}
        except Exception as exc:
            logger.exception("Failed to move mouse: %s", exc)
            return {"success": False, "error": str(exc)}

    def schema(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "description": self.description,
            "parameters": {
                "type": "object",
                "properties": {
                    "x": {"type": "integer", "description": "Tọa độ X"},
                    "y": {"type": "integer", "description": "Tọa độ Y"},
                },
                "required": ["x", "y"],
            },
        }


class ClickTool(Tool):
    """Perform a left click at the current cursor position."""

    name = "click"
    description = "Nhấn chuột trái tại vị trí hiện tại"

    def run(self, x: int, y: int) -> dict:
        try:
            win32api.SetCursorPos((int(x), int(y)))
            win32api.mouse_event(win32con.MOUSEEVENTF_LEFTDOWN, 0, 0, 0, 0)
            win32api.mouse_event(win32con.MOUSEEVENTF_LEFTUP, 0, 0, 0, 0)
            return {"success": True, "x": int(x), "y": int(y)}
        except Exception as exc:
            logger.exception("Failed to click: %s", exc)
            return {"success": False, "error": str(exc)}

    def schema(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "description": self.description,
            "parameters": {
                "type": "object",
                "properties": {
                    "x": {"type": "integer", "description": "Tọa độ X"},
                    "y": {"type": "integer", "description": "Tọa độ Y"},
                },
                "required": ["x", "y"],
            },
        }


class DoubleClickTool(Tool):
    """Perform a double left click at a target coordinate."""

    name = "double_click"
    description = "Nhấn đúp chuột trái tại vị trí được chỉ định"

    def run(self, x: int, y: int) -> dict:
        try:
            win32api.SetCursorPos((int(x), int(y)))
            for _ in range(2):
                win32api.mouse_event(win32con.MOUSEEVENTF_LEFTDOWN, 0, 0, 0, 0)
                win32api.mouse_event(win32con.MOUSEEVENTF_LEFTUP, 0, 0, 0, 0)
                time.sleep(0.05)
            return {"success": True, "x": int(x), "y": int(y)}
        except Exception as exc:
            logger.exception("Failed to double click: %s", exc)
            return {"success": False, "error": str(exc)}

    def schema(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "description": self.description,
            "parameters": {
                "type": "object",
                "properties": {
                    "x": {"type": "integer", "description": "Tọa độ X"},
                    "y": {"type": "integer", "description": "Tọa độ Y"},
                },
                "required": ["x", "y"],
            },
        }


class RightClickTool(Tool):
    """Perform a right click at a target coordinate."""

    name = "right_click"
    description = "Nhấn chuột phải tại vị trí được chỉ định"

    def run(self, x: int, y: int) -> dict:
        try:
            win32api.SetCursorPos((int(x), int(y)))
            win32api.mouse_event(win32con.MOUSEEVENTF_RIGHTDOWN, 0, 0, 0, 0)
            win32api.mouse_event(win32con.MOUSEEVENTF_RIGHTUP, 0, 0, 0, 0)
            return {"success": True, "x": int(x), "y": int(y)}
        except Exception as exc:
            logger.exception("Failed to right click: %s", exc)
            return {"success": False, "error": str(exc)}

    def schema(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "description": self.description,
            "parameters": {
                "type": "object",
                "properties": {
                    "x": {"type": "integer", "description": "Tọa độ X"},
                    "y": {"type": "integer", "description": "Tọa độ Y"},
                },
                "required": ["x", "y"],
            },
        }


class DragTool(Tool):
    """Drag the cursor from one coordinate to another."""

    name = "drag"
    description = "Kéo chuột từ điểm bắt đầu tới điểm kết thúc"

    def run(self, start_x: int, start_y: int, end_x: int, end_y: int) -> dict:
        try:
            win32api.SetCursorPos((int(start_x), int(start_y)))
            win32api.mouse_event(win32con.MOUSEEVENTF_LEFTDOWN, 0, 0, 0, 0)
            win32api.SetCursorPos((int(end_x), int(end_y)))
            win32api.mouse_event(win32con.MOUSEEVENTF_LEFTUP, 0, 0, 0, 0)
            return {"success": True, "start": {"x": int(start_x), "y": int(start_y)}, "end": {"x": int(end_x), "y": int(end_y)}}
        except Exception as exc:
            logger.exception("Failed to drag: %s", exc)
            return {"success": False, "error": str(exc)}

    def schema(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "description": self.description,
            "parameters": {
                "type": "object",
                "properties": {
                    "start_x": {"type": "integer", "description": "Tọa độ X bắt đầu"},
                    "start_y": {"type": "integer", "description": "Tọa độ Y bắt đầu"},
                    "end_x": {"type": "integer", "description": "Tọa độ X kết thúc"},
                    "end_y": {"type": "integer", "description": "Tọa độ Y kết thúc"},
                },
                "required": ["start_x", "start_y", "end_x", "end_y"],
            },
        }


class MouseTool(Tool):
    """Unified mouse controller supporting action-based operations."""

    name = "mouse"
    description = "Điều khiển chuột Windows theo action: move, click, double_click, right_click, middle_click, drag, scroll, get_position"

    SUPPORTED_ACTIONS = {
        "move",
        "click",
        "double_click",
        "right_click",
        "middle_click",
        "drag",
        "scroll",
        "get_position",
    }

    def run(
        self,
        action: str,
        x: Optional[int] = None,
        y: Optional[int] = None,
        dx: Optional[int] = None,
        dy: Optional[int] = None,
        from_x: Optional[int] = None,
        from_y: Optional[int] = None,
        to_x: Optional[int] = None,
        to_y: Optional[int] = None,
        amount: Optional[int] = None,
        relative: bool = False,
    ) -> dict:
        try:
            action_name = str(action or "").strip().lower()
            if action_name not in self.SUPPORTED_ACTIONS:
                raise ValueError(f"Unsupported mouse action: {action}")

            if action_name == "move":
                logger.info("[MOUSE] Move")
                start_x, start_y = self._get_cursor_position()
                if relative:
                    target_x = start_x + int(dx or 0)
                    target_y = start_y + int(dy or 0)
                else:
                    target_x = int(x) if x is not None else start_x
                    target_y = int(y) if y is not None else start_y
                self._set_cursor_pos(target_x, target_y)
                return {"success": True, "result": f"Moved cursor to ({target_x}, {target_y})", "data": {"x": target_x, "y": target_y}, "error": None}

            if action_name == "click":
                logger.info("[MOUSE] Click")
                target_x, target_y = self._resolve_coordinates(x, y)
                self._set_cursor_pos(target_x, target_y)
                self._mouse_event(win32con.MOUSEEVENTF_LEFTDOWN)
                self._mouse_event(win32con.MOUSEEVENTF_LEFTUP)
                return {"success": True, "result": f"Clicked at ({target_x}, {target_y})", "data": {"x": target_x, "y": target_y}, "error": None}

            if action_name == "double_click":
                logger.info("[MOUSE] Double Click")
                target_x, target_y = self._resolve_coordinates(x, y)
                self._set_cursor_pos(target_x, target_y)
                for _ in range(2):
                    self._mouse_event(win32con.MOUSEEVENTF_LEFTDOWN)
                    self._mouse_event(win32con.MOUSEEVENTF_LEFTUP)
                    time.sleep(0.05)
                return {"success": True, "result": f"Double-clicked at ({target_x}, {target_y})", "data": {"x": target_x, "y": target_y}, "error": None}

            if action_name == "right_click":
                logger.info("[MOUSE] Right Click")
                target_x, target_y = self._resolve_coordinates(x, y)
                self._set_cursor_pos(target_x, target_y)
                self._mouse_event(win32con.MOUSEEVENTF_RIGHTDOWN)
                self._mouse_event(win32con.MOUSEEVENTF_RIGHTUP)
                return {"success": True, "result": f"Right-clicked at ({target_x}, {target_y})", "data": {"x": target_x, "y": target_y}, "error": None}

            if action_name == "middle_click":
                logger.info("[MOUSE] Middle Click")
                target_x, target_y = self._resolve_coordinates(x, y)
                self._set_cursor_pos(target_x, target_y)
                self._mouse_event(win32con.MOUSEEVENTF_MIDDLEDOWN)
                self._mouse_event(win32con.MOUSEEVENTF_MIDDLEUP)
                return {"success": True, "result": f"Middle-clicked at ({target_x}, {target_y})", "data": {"x": target_x, "y": target_y}, "error": None}

            if action_name == "drag":
                logger.info("[MOUSE] Drag")
                from_x_value = int(from_x) if from_x is not None else self._get_cursor_position()[0]
                from_y_value = int(from_y) if from_y is not None else self._get_cursor_position()[1]
                to_x_value = int(to_x) if to_x is not None else from_x_value
                to_y_value = int(to_y) if to_y is not None else from_y_value
                self._set_cursor_pos(from_x_value, from_y_value)
                self._mouse_event(win32con.MOUSEEVENTF_LEFTDOWN)
                self._set_cursor_pos(to_x_value, to_y_value)
                self._mouse_event(win32con.MOUSEEVENTF_LEFTUP)
                return {
                    "success": True,
                    "result": f"Dragged from ({from_x_value}, {from_y_value}) to ({to_x_value}, {to_y_value})",
                    "data": {"from_x": from_x_value, "from_y": from_y_value, "to_x": to_x_value, "to_y": to_y_value},
                    "error": None,
                }

            if action_name == "scroll":
                logger.info("[MOUSE] Scroll amount=%s", amount)
                delta = int(amount or 0)
                if delta == 0:
                    raise ValueError("amount không được bằng 0")
                self._mouse_event(win32con.MOUSEEVENTF_WHEEL, data=delta)
                return {"success": True, "result": f"Scrolled by {delta}", "data": {"amount": delta}, "error": None}

            if action_name == "get_position":
                logger.info("[MOUSE] Get Position")
                position = self._get_cursor_position()
                return {"success": True, "result": f"Cursor position: ({position[0]}, {position[1]})", "data": {"x": position[0], "y": position[1]}, "error": None}

            raise ValueError(f"Unsupported mouse action: {action}")
        except Exception as exc:
            logger.exception("[MOUSE] action=%s failed: %s", action, exc)
            return {"success": False, "result": "", "data": {"action": action}, "error": str(exc)}

    def schema(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "description": self.description,
            "parameters": {
                "type": "object",
                "properties": {
                    "action": {"type": "string", "description": "Tên hành động: move, click, double_click, right_click, middle_click, drag, scroll, get_position"},
                    "x": {"type": "integer", "description": "Tọa độ tuyệt đối X"},
                    "y": {"type": "integer", "description": "Tọa độ tuyệt đối Y"},
                    "dx": {"type": "integer", "description": "Độ lệch tương đối theo chiều ngang"},
                    "dy": {"type": "integer", "description": "Độ lệch tương đối theo chiều dọc"},
                    "from_x": {"type": "integer", "description": "Tọa độ bắt đầu X cho drag"},
                    "from_y": {"type": "integer", "description": "Tọa độ bắt đầu Y cho drag"},
                    "to_x": {"type": "integer", "description": "Tọa độ kết thúc X cho drag"},
                    "to_y": {"type": "integer", "description": "Tọa độ kết thúc Y cho drag"},
                    "amount": {"type": "integer", "description": "Số lượng cuộn chuột, ví dụ -600"},
                    "relative": {"type": "boolean", "description": "Nếu true, x/y sẽ được xem như điểm tương đối so với vị trí hiện tại"},
                },
                "required": ["action"],
            },
        }

    def _resolve_coordinates(self, x: Optional[int], y: Optional[int]) -> Tuple[int, int]:
        if x is None and y is None:
            return self._get_cursor_position()
        if x is None or y is None:
            current_x, current_y = self._get_cursor_position()
            return (int(x) if x is not None else current_x, int(y) if y is not None else current_y)
        return int(x), int(y)

    def _set_cursor_pos(self, x: int, y: int) -> None:
        win32api.SetCursorPos((int(x), int(y)))

    def _get_cursor_position(self) -> Tuple[int, int]:
        return win32api.GetCursorPos()

    def _mouse_event(self, event_flag: int, data: int = 0) -> None:
        win32api.mouse_event(event_flag, 0, 0, data, 0)
