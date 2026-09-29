import csv
import logging
import os
import subprocess
import time
from typing import Any, Dict, Optional, Tuple

import win32api
import win32gui
import win32process

from src.tools.base import Tool

logger = logging.getLogger(__name__)


class LaunchAppTool(Tool):
    """Launch an application by name or executable path."""

    name = "launch_app"
    description = "Mở một ứng dụng trên Windows bằng tên hoặc đường dẫn đến file thực thi"

    def run(self, app_name_or_path: str) -> dict:
        try:
            if not app_name_or_path or not str(app_name_or_path).strip():
                raise ValueError("app_name_or_path không được rỗng")

            target = str(app_name_or_path).strip()
            normalized = self._normalize_target(target)
            logger.info("[LAUNCH] requested: %s", target)

            existing = self._find_running_process(normalized)
            if existing:
                pid, process_name = existing
                hwnd = self._wait_for_window(pid=pid, target_name=normalized, title_hint=target)
                title = self._get_window_title(hwnd)
                if hwnd is not None:
                    self._focus_window(hwnd)
                    logger.info("[LAUNCH] found running %s pid=%s hwnd=%s title=%s", process_name, pid, hwnd, title)
                    return {
                        "success": True,
                        "result": "Focused existing Chrome window" if process_name == "chrome.exe" else f"Focused existing {process_name} window",
                        "data": {
                            "target": target,
                            "pid": pid,
                            "hwnd": hwnd,
                            "process_name": process_name,
                            "executable_name": process_name,
                            "title": title,
                            "action": "focused_existing",
                        },
                    }

                logger.warning("[LAUNCH] found running %s pid=%s but no visible window could be focused", process_name, pid)
                return {
                    "success": False,
                    "result": f"No visible window found for running {process_name}",
                    "data": {
                        "target": target,
                        "pid": pid,
                        "hwnd": None,
                        "process_name": process_name,
                        "executable_name": process_name,
                        "title": None,
                        "action": "existing_running",
                    },
                    "error": f"Không thể focus cửa sổ đang chạy cho {process_name}",
                }

            os.startfile(target)

            logger.info("[LAUNCH] requested launch for %s", target)
            pid, process_name = self._wait_for_process(normalized)
            hwnd = self._wait_for_window(pid=pid, target_name=normalized, title_hint=target) if pid else self._wait_for_window(pid=None, target_name=normalized, title_hint=target)
            title = self._get_window_title(hwnd)
            if hwnd:
                logger.info("[LAUNCH] pid=%s hwnd=%s process=%s title=%s", pid, hwnd, process_name, title)
            else:
                logger.warning("[LAUNCH] no window found after launch pid=%s process=%s target=%s", pid, process_name, target)

            return {
                "success": bool(hwnd),
                "result": f"Launch requested: {target}" if hwnd else f"Launch failed for: {target}",
                "data": {
                    "target": target,
                    "pid": pid,
                    "hwnd": hwnd,
                    "process_name": process_name,
                    "executable_name": process_name,
                    "title": title,
                    "action": "launched",
                },
            }
        except Exception as exc:
            logger.exception("Failed to launch application: %s", exc)
            return {"success": False, "error": f"Không thể mở ứng dụng: {exc}", "data": {"target": app_name_or_path}}

    def schema(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "description": self.description,
            "parameters": {
                "type": "object",
                "properties": {
                    "app_name_or_path": {
                        "type": "string",
                        "description": "Tên ứng dụng hoặc đường dẫn đầy đủ tới file thực thi",
                    }
                },
                "required": ["app_name_or_path"],
            },
        }

    def _normalize_target(self, target: str) -> str:
        cleaned = os.path.splitext(os.path.basename(target.strip()))[0].lower()
        aliases = {
            "calculator": "calculator.exe",
            "calc": "calculator.exe",
            "spotify": "spotify.exe",
            "notepad": "notepad.exe",
            "code": "code.exe",
            "vscode": "code.exe",
            "visual studio code": "code.exe",
        }
        return aliases.get(cleaned, f"{cleaned}.exe")

    def _find_running_process(self, normalized_target: str) -> Optional[Tuple[int, str]]:
        try:
            result = subprocess.run(["tasklist", "/fo", "csv", "/nh"], capture_output=True, text=True, check=False)
            if result.returncode != 0:
                return None
            rows = list(csv.reader(result.stdout.splitlines()))
            target = normalized_target.lower()
            for row in rows:
                if not row:
                    continue
                process_name = row[0].strip().strip('"').lower()
                if process_name == target or process_name == target.replace(".exe", ""):
                    pid_value = row[1].strip().strip('"') if len(row) > 1 else ""
                    try:
                        return int(pid_value), process_name
                    except ValueError:
                        return None
        except Exception:
            return None
        return None

    def _wait_for_process(self, normalized_target: str, timeout: float = 5.0) -> Tuple[Optional[int], Optional[str]]:
        deadline = time.time() + timeout
        while time.time() < deadline:
            existing = self._find_running_process(normalized_target)
            if existing:
                return existing
            time.sleep(0.2)
        return None, None

    def _wait_for_window(self, pid: Optional[int], target_name: Optional[str] = None, title_hint: Optional[str] = None, timeout: float = 10.0) -> Optional[int]:
        deadline = time.time() + timeout
        while time.time() < deadline:
            candidate = self._find_window_for_target(pid=pid, target_name=target_name or title_hint)
            if candidate is not None:
                logger.info("[WINDOW] hwnd found=%s pid=%s target=%s", candidate, pid, target_name or title_hint)
                return candidate
            time.sleep(0.2)
        logger.warning("[WINDOW] no hwnd found before timeout pid=%s target=%s", pid, target_name or title_hint)
        return None

    def _find_window_for_target(self, pid: Optional[int], target_name: Optional[str]) -> Optional[int]:
        target = str(target_name or "").strip().lower()
        target_names = {target}
        if target:
            base_name = os.path.splitext(os.path.basename(target))[0].lower()
            if base_name:
                target_names.add(base_name)
            if target.endswith(".exe"):
                target_names.add(target[:-4])
            else:
                target_names.add(f"{target}.exe")

        candidates = []

        def enum_handler(handle, _):
            if not win32gui.IsWindowVisible(handle):
                return
            title = self._get_window_title(handle) or ""
            class_name = self._get_class_name(handle) or ""
            current_pid = self._get_pid_for_window(handle)
            process_name = self._get_process_name_for_window(handle)
            logger.info("[WINDOW] hwnd=%s pid=%s class=%s title=%r process=%r", handle, current_pid, class_name, title, process_name)

            score = 0
            if pid is not None and current_pid == pid:
                score += 100

            if process_name:
                proc = process_name.lower()
                if proc in target_names:
                    score += 90
                elif proc.replace(".exe", "") in target_names:
                    score += 85

            title_lower = title.lower()
            for token in target_names:
                if token and token in title_lower:
                    score += 40
                    break

            class_lower = class_name.lower()
            for token in target_names:
                if token and token in class_lower:
                    score += 20
                    break

            if title and score > 0:
                rect = self._get_window_rect(handle)
                area = max(0, rect[2] - rect[0]) * max(0, rect[3] - rect[1]) if rect else 0
                if area > 0:
                    candidates.append((score, area, handle))

        win32gui.EnumWindows(enum_handler, None)
        if not candidates:
            return None
        candidates.sort(key=lambda item: (item[0], item[1]), reverse=True)
        return candidates[0][2]

    def _get_window_title(self, hwnd: Optional[int]) -> Optional[str]:
        if hwnd is None:
            return None
        try:
            title = win32gui.GetWindowText(hwnd)
            return title or None
        except Exception:
            return None

    def _get_class_name(self, hwnd: Optional[int]) -> Optional[str]:
        if hwnd is None:
            return None
        try:
            return win32gui.GetClassName(hwnd) or None
        except Exception:
            return None

    def _get_pid_for_window(self, hwnd: Optional[int]) -> Optional[int]:
        if hwnd is None:
            return None
        try:
            _, pid = win32process.GetWindowThreadProcessId(hwnd)
            return pid
        except Exception:
            return None

    def _get_process_name_for_window(self, hwnd: Optional[int]) -> Optional[str]:
        pid = self._get_pid_for_window(hwnd)
        if pid is None:
            return None
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

    def _get_window_rect(self, hwnd: Optional[int]) -> Optional[Tuple[int, int, int, int]]:
        if hwnd is None:
            return None
        try:
            return win32gui.GetWindowRect(hwnd)
        except Exception:
            return None

    def _focus_window(self, hwnd: Optional[int]) -> None:
        if hwnd is None:
            return
        if win32gui.IsIconic(hwnd):
            win32gui.ShowWindow(hwnd, 9)
        win32gui.BringWindowToTop(hwnd)
        win32gui.SetForegroundWindow(hwnd)
        win32gui.SetActiveWindow(hwnd)

