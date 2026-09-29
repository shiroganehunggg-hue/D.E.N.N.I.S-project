import logging
import os
import time
from typing import Any, Dict, List, Optional

import win32api
import win32con
import win32gui
import win32process

from src.tools.base import Tool

logger = logging.getLogger(__name__)


class ListWindowsTool(Tool):
    """List top-level windows available on the desktop."""

    name = "list_windows"
    description = "Liệt kê các cửa sổ đang có trên hệ thống"

    def run(self) -> dict:
        try:
            windows: List[Dict[str, Any]] = []
            def enum_handler(hwnd, _):
                if win32gui.IsWindowVisible(hwnd):
                    title = win32gui.GetWindowText(hwnd)
                    if title:
                        windows.append({"hwnd": hwnd, "title": title})
            win32gui.EnumWindows(enum_handler, None)
            return {"success": True, "windows": windows}
        except Exception as exc:
            logger.exception("Failed to list windows: %s", exc)
            return {"success": False, "error": str(exc)}

    def schema(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "description": self.description,
            "parameters": {"type": "object", "properties": {}, "required": []},
        }


class FindWindowTool(Tool):
    """Find a window by a case-insensitive substring in its title."""

    name = "find_window"
    description = "Tìm cửa sổ theo tiêu đề"

    def run(self, title: str) -> dict:
        try:
            if not title or not str(title).strip():
                raise ValueError("title không được rỗng")
            target = str(title).strip().lower()
            matches: List[Dict[str, Any]] = []
            def enum_handler(hwnd, _):
                if win32gui.IsWindowVisible(hwnd):
                    current_title = win32gui.GetWindowText(hwnd)
                    if target in current_title.lower():
                        matches.append({"hwnd": hwnd, "title": current_title})
            win32gui.EnumWindows(enum_handler, None)
            return {"success": True, "matches": matches}
        except Exception as exc:
            logger.exception("Failed to find window: %s", exc)
            return {"success": False, "error": str(exc)}

    def schema(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "description": self.description,
            "parameters": {
                "type": "object",
                "properties": {"title": {"type": "string", "description": "Chuỗi tìm kiếm trong tiêu đề cửa sổ"}},
                "required": ["title"],
            },
        }


class FocusWindowTool(Tool):
    """Bring a window to the foreground using hwnd/process/class/title fallbacks."""

    name = "focus_window"
    description = "Đưa một cửa sổ lên trước"

    def run(self, hwnd: Optional[int] = None, title: str = "", process_name: str = "", executable_name: str = "", class_name: str = "") -> dict:
        try:
            target_hwnd = None
            reason = "no candidate"

            if hwnd is not None:
                target_hwnd = self._resolve_hwnd(hwnd=hwnd)
                reason = "hwnd"
            if target_hwnd is None and process_name:
                target_hwnd = self.find_window_by_process(process_name)
                reason = "process"
            if target_hwnd is None and executable_name:
                target_hwnd = self.find_window_by_process(executable_name)
                reason = "executable"
            if target_hwnd is None and class_name:
                target_hwnd = self.find_window_by_class(class_name)
                reason = "class"
            if target_hwnd is None and title:
                target_hwnd = self._find_window_by_title(title)
                reason = "title"

            if target_hwnd is None:
                logger.warning("[FOCUS] window not found. hwnd=%s title=%s process=%s executable=%s class=%s reason=%s", hwnd, title, process_name, executable_name, class_name, reason)
                return {"success": False, "error": f"Không tìm thấy cửa sổ cho: {title or process_name or executable_name or class_name or hwnd}", "data": {"hwnd": hwnd, "title": title, "process_name": process_name, "executable_name": executable_name, "class_name": class_name, "reason": reason}}

            title_text = self._get_window_title(target_hwnd) or title or ""
            logger.info("[FOCUS] using %s match hwnd=%s title=%s", reason, target_hwnd, title_text)

            success = self._focus_window(target_hwnd)
            if success:
                logger.info("[FOCUS] success hwnd=%s title=%s", target_hwnd, title_text)
                return {"success": True, "result": f"Đã focus cửa sổ {title_text}", "data": {"title": title_text, "hwnd": target_hwnd, "process_name": process_name, "executable_name": executable_name, "class_name": class_name, "reason": reason}}

            logger.warning("[FOCUS] failed hwnd=%s title=%s", target_hwnd, title_text)
            return {"success": False, "error": f"Không thể đưa cửa sổ lên foreground: {title or process_name or executable_name or class_name or hwnd}", "data": {"title": title_text, "hwnd": target_hwnd, "process_name": process_name, "executable_name": executable_name, "class_name": class_name, "reason": reason}}
        except Exception as exc:
            logger.exception("Failed to focus window: %s", exc)
            return {"success": False, "error": str(exc), "data": {"hwnd": hwnd, "title": title, "process_name": process_name, "executable_name": executable_name, "class_name": class_name}}

    def schema(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "description": self.description,
            "parameters": {
                "type": "object",
                "properties": {
                    "hwnd": {"type": "integer", "description": "HWND của cửa sổ đã biết trước"},
                    "title": {"type": "string", "description": "Tiêu đề cửa sổ, dùng cuối cùng nếu không có thông tin khác"},
                    "process_name": {"type": "string", "description": "Tên tiến trình, ví dụ notepad.exe"},
                    "executable_name": {"type": "string", "description": "Tên file thực thi, ví dụ notepad"},
                    "class_name": {"type": "string", "description": "Tên lớp cửa sổ"},
                },
                "required": [],
            },
        }

    def _resolve_hwnd(self, hwnd: Optional[int]) -> Optional[int]:
        if hwnd is None:
            return None
        if self._is_window_candidate(hwnd):
            return hwnd
        return None

    def _find_window_by_title(self, title: str) -> Optional[int]:
        target = str(title).strip().lower()
        candidates: List[tuple[int, int]] = []
        def enum_handler(handle, _):
            if not self._is_window_candidate(handle):
                return
            current_title = self._get_window_title(handle) or ""
            if current_title.lower().find(target) >= 0:
                candidates.append((self._get_window_area(handle), handle))
        win32gui.EnumWindows(enum_handler, None)
        if not candidates:
            return None
        candidates.sort(key=lambda item: item[0], reverse=True)
        return candidates[0][1]

    def find_window_by_process(self, process_name: str) -> Optional[int]:
        target = str(process_name).strip().lower()
        candidates: List[tuple[int, int]] = []
        def enum_handler(handle, _):
            if not self._is_window_candidate(handle):
                return
            pid = self._get_pid_for_window(handle)
            if pid is None:
                return
            current_process = self._get_process_name(pid)
            if current_process and (current_process.lower() == target or current_process.lower() == target.replace(".exe", "")):
                candidates.append((self._get_window_area(handle), handle))
        win32gui.EnumWindows(enum_handler, None)
        if not candidates:
            return None
        candidates.sort(key=lambda item: item[0], reverse=True)
        return candidates[0][1]

    def find_window_by_class(self, class_name: str) -> Optional[int]:
        target = str(class_name).strip().lower()
        candidates: List[tuple[int, int]] = []
        def enum_handler(handle, _):
            if not self._is_window_candidate(handle):
                return
            try:
                current_class = win32gui.GetClassName(handle)
            except Exception:
                current_class = ""
            if current_class.lower() == target:
                candidates.append((self._get_window_area(handle), handle))
        win32gui.EnumWindows(enum_handler, None)
        if not candidates:
            return None
        candidates.sort(key=lambda item: item[0], reverse=True)
        return candidates[0][1]

    def _is_window_candidate(self, hwnd: int) -> bool:
        if hwnd is None:
            return False
        if not win32gui.IsWindowVisible(hwnd):
            return False
        if not win32gui.IsWindowEnabled(hwnd):
            return False
        title = self._get_window_title(hwnd)
        if not title:
            return False
        if not self._get_window_area(hwnd):
            return False
        return True

    def _get_pid_for_window(self, hwnd: int) -> Optional[int]:
        try:
            _, pid = win32process.GetWindowThreadProcessId(hwnd)
            return pid
        except Exception:
            return None

    def _get_window_area(self, hwnd: int) -> int:
        try:
            left, top, right, bottom = win32gui.GetWindowRect(hwnd)
            width = max(0, right - left)
            height = max(0, bottom - top)
            return width * height
        except Exception:
            return 0

    def _get_window_title(self, hwnd: Optional[int]) -> Optional[str]:
        if hwnd is None:
            return None
        try:
            title = win32gui.GetWindowText(hwnd)
            return title.strip() or None
        except Exception:
            return None

    def _get_process_name(self, pid: int) -> Optional[str]:
        try:
            handle = win32api.OpenProcess(0x0400 | 0x00100000, False, pid)
            if not handle:
                return None
            try:
                path = win32process.GetModuleFileNameEx(handle, 0)
                return os.path.basename(path).lower()
            finally:
                try:
                    win32api.CloseHandle(handle)
                except Exception:
                    pass
        except Exception:
            return None

    def _focus_window(self, hwnd: int) -> bool:
        if hwnd is None:
            return False
        for attempt in range(4):
            logger.info("[FOCUS] retry... attempt=%s hwnd=%s", attempt + 1, hwnd)
            if win32gui.IsIconic(hwnd):
                win32gui.ShowWindow(hwnd, win32con.SW_RESTORE)
            win32gui.BringWindowToTop(hwnd)
            win32gui.ShowWindow(hwnd, win32con.SW_SHOW)
            win32gui.SetForegroundWindow(hwnd)
            win32gui.SetActiveWindow(hwnd)
            win32gui.SetWindowPos(hwnd, win32con.HWND_TOPMOST, 0, 0, 0, 0, win32con.SWP_NOMOVE | win32con.SWP_NOSIZE)
            win32gui.SetWindowPos(hwnd, win32con.HWND_NOTOPMOST, 0, 0, 0, 0, win32con.SWP_NOMOVE | win32con.SWP_NOSIZE)
            time.sleep(0.2)
            foreground = win32gui.GetForegroundWindow()
            active = win32gui.GetActiveWindow()
            if foreground == hwnd or active == hwnd:
                return True
        return False


class CloseWindowTool(Tool):
    """Close a window by title."""

    name = "close_window"
    description = "Đóng một cửa sổ"

    def run(self, title: str) -> str:
        try:
            hwnd = self._find_window_hwnd(title)
            if hwnd is None:
                return str({"success": False, "error": f"Không tìm thấy cửa sổ: {title}"})
            win32gui.PostMessage(hwnd, win32con.WM_CLOSE, 0, 0)
            return str({"success": True, "title": title})
        except Exception as exc:
            logger.exception("Failed to close window: %s", exc)
            return str({"success": False, "error": str(exc)})

    def schema(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "description": self.description,
            "parameters": {"type": "object", "properties": {"title": {"type": "string", "description": "Tiêu đề cửa sổ cần đóng"}}, "required": ["title"]},
        }

    def _find_window_hwnd(self, title: str) -> Optional[int]:
        target = str(title).strip().lower()
        hwnd: Optional[int] = None
        def enum_handler(handle, _):
            nonlocal hwnd
            if hwnd is not None:
                return
            if win32gui.IsWindowVisible(handle):
                current_title = win32gui.GetWindowText(handle)
                if target in current_title.lower():
                    hwnd = handle
        win32gui.EnumWindows(enum_handler, None)
        return hwnd


class MaximizeWindowTool(Tool):
    """Maximize a window by title."""

    name = "maximize_window"
    description = "Phóng to cửa sổ"

    def run(self, title: str) -> str:
        try:
            hwnd = self._find_window_hwnd(title)
            if hwnd is None:
                return str({"success": False, "error": f"Không tìm thấy cửa sổ: {title}"})
            win32gui.ShowWindow(hwnd, win32con.SW_MAXIMIZE)
            return str({"success": True, "title": title})
        except Exception as exc:
            logger.exception("Failed to maximize window: %s", exc)
            return str({"success": False, "error": str(exc)})

    def schema(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "description": self.description,
            "parameters": {"type": "object", "properties": {"title": {"type": "string", "description": "Tiêu đề cửa sổ cần phóng to"}}, "required": ["title"]},
        }

    def _find_window_hwnd(self, title: str) -> Optional[int]:
        target = str(title).strip().lower()
        hwnd: Optional[int] = None
        def enum_handler(handle, _):
            nonlocal hwnd
            if hwnd is not None:
                return
            if win32gui.IsWindowVisible(handle):
                current_title = win32gui.GetWindowText(handle)
                if target in current_title.lower():
                    hwnd = handle
        win32gui.EnumWindows(enum_handler, None)
        return hwnd


class MinimizeWindowTool(Tool):
    """Minimize a window by title."""

    name = "minimize_window"
    description = "Thu nhỏ cửa sổ"

    def run(self, title: str) -> str:
        try:
            hwnd = self._find_window_hwnd(title)
            if hwnd is None:
                return str({"success": False, "error": f"Không tìm thấy cửa sổ: {title}"})
            win32gui.ShowWindow(hwnd, win32con.SW_MINIMIZE)
            return str({"success": True, "title": title})
        except Exception as exc:
            logger.exception("Failed to minimize window: %s", exc)
            return str({"success": False, "error": str(exc)})

    def schema(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "description": self.description,
            "parameters": {"type": "object", "properties": {"title": {"type": "string", "description": "Tiêu đề cửa sổ cần thu nhỏ"}}, "required": ["title"]},
        }

    def _find_window_hwnd(self, title: str) -> Optional[int]:
        target = str(title).strip().lower()
        hwnd: Optional[int] = None
        def enum_handler(handle, _):
            nonlocal hwnd
            if hwnd is not None:
                return
            if win32gui.IsWindowVisible(handle):
                current_title = win32gui.GetWindowText(handle)
                if target in current_title.lower():
                    hwnd = handle
        win32gui.EnumWindows(enum_handler, None)
        return hwnd
