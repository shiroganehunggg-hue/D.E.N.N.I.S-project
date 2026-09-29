from __future__ import annotations

import os
import subprocess
import time
from urllib.parse import quote_plus

from src.tools.base import Tool
from src.tools.vision.vision import LocateTextTool
from src.tools.windows.keyboard import HotkeyTool, PressKeyTool, TypeTextTool
from src.tools.windows.mouse import ClickTool
from src.tools.windows.windows import FocusWindowTool


class SpotifyTool(Tool):
    """Open Spotify and perform simple playback/search actions on the desktop app."""

    name = "spotify"
    description = (
        "Mở Spotify desktop và thực hiện tìm / phát bài nhạc theo tên bài hoặc query. "
        "Hỗ trợ action: open, search, play."
    )
    enabled = True

    def run(self, action: str = "open", query: str = "", track_name: str = "", artist: str = "") -> dict:
        action_name = (action or "open").strip().lower()
        if action_name not in {"open", "search", "play"}:
            return {
                "success": False,
                "error": f"Unsupported spotify action: {action_name}",
                "data": {"action": action_name},
            }

        spotify_exe = self._find_spotify_executable()
        if not spotify_exe:
            return {
                "success": False,
                "error": "Không tìm thấy Spotify desktop trên máy. Hãy cài đặt Spotify hoặc kiểm tra đường dẫn exe.",
                "data": {"action": action_name},
            }

        try:
            os.startfile(spotify_exe)
        except Exception as exc:
            return {"success": False, "error": f"Không thể mở Spotify: {exc}", "data": {"action": action_name}}

        if not self._process_started("spotify.exe", timeout=8.0):
            return {
                "success": False,
                "error": "Spotify được gọi khởi động nhưng tiến trình không xuất hiện, có thể app chưa cài đúng hoặc bị lỗi.",
                "data": {"action": action_name, "exe": spotify_exe},
            }

        if action_name == "open":
            return {
                "success": True,
                "result": "Spotify đã được mở.",
                "data": {"action": "open", "exe": spotify_exe},
                "error": None,
            }

        target_query = (query or track_name or "").strip()
        if artist and target_query:
            target_query = f"{target_query} {artist}".strip()
        if not target_query:
            return {
                "success": False,
                "error": "Thiếu query hoặc tên bài để tìm trên Spotify.",
                "data": {"action": action_name, "exe": spotify_exe},
            }

        focus_result = FocusWindowTool().run(process_name="spotify.exe")
        if not focus_result.get("success"):
            return {
                "success": False,
                "error": "Spotify đang chạy nhưng không thể focus cửa sổ để tìm bài.",
                "data": {"action": action_name, "query": target_query, "focus": focus_result},
            }

        search_result = HotkeyTool().run(keys=["ctrl", "k"])
        if not search_result.get("success"):
            return {"success": False, "error": "Không thể mở ô tìm kiếm Spotify.", "data": search_result}
        time.sleep(0.2)
        type_result = TypeTextTool().run(target_query)
        if not isinstance(type_result, dict) or not type_result.get("success"):
            return {"success": False, "error": "Không thể nhập truy vấn vào Spotify.", "data": type_result}
        enter_result = PressKeyTool().run("enter")
        if not enter_result.get("success"):
            return {"success": False, "error": "Không thể gửi truy vấn tìm kiếm Spotify.", "data": enter_result}

        time.sleep(2.0)
        locate_result = LocateTextTool().run(target_query)
        matches = locate_result.get("bounding_boxes", []) if locate_result.get("success") else []
        try:
            import win32gui

            hwnd = win32gui.GetForegroundWindow()
            left, top, right, bottom = 0, 0, 0, 0
            if hwnd:
                left, top, right, bottom = win32gui.GetWindowRect(hwnd)
        except Exception:
            left, top, right, bottom = 0, 0, 0, 0

        row_matches = [
            box
            for box in matches
            if box.get("y", 0) > top + 100
            and (not bottom or box.get("y", 0) < bottom - 80)
            and box.get("x", 0) >= left
            and (not right or box.get("x", 0) < right)
        ]
        if action_name == "search":
            return {
                "success": True,
                "result": f"Đã tìm {target_query} trên Spotify.",
                "data": {"action": "search", "query": target_query, "results_found": len(row_matches), "exe": spotify_exe},
                "error": None,
            }

        if not row_matches:
            return {
                "success": False,
                "error": "Spotify đã nhận truy vấn nhưng không tìm thấy tên bài trên màn hình để chọn.",
                "data": {"action": action_name, "query": target_query, "playback_confirmed": False, "ocr": locate_result},
            }

        target_box = min(row_matches, key=lambda box: box["y"])
        x = target_box["x"] + target_box["width"] // 2
        y = target_box["y"] + target_box["height"] // 2
        click_result = ClickTool().run(x, y)
        if not click_result.get("success"):
            return {"success": False, "error": "Tìm thấy bài nhưng không thể chọn kết quả.", "data": click_result}
        time.sleep(0.15)
        second_click = ClickTool().run(x, y)
        if not second_click.get("success"):
            return {"success": False, "error": "Đã chọn kết quả nhưng không thể gửi lệnh phát.", "data": second_click}

        time.sleep(1.5)
        playback_confirmed = self._playback_visible()
        return {
            "success": True,
            "result": (
                f"Spotify đang phát: {target_query}"
                if playback_confirmed
                else f"Đã chọn {target_query} trong Spotify; chưa xác minh được trạng thái đang phát."
            ),
            "data": {
                "action": action_name,
                "query": target_query,
                "selected_result": target_box,
                "playback_confirmed": playback_confirmed,
                "exe": spotify_exe,
            },
            "error": None,
        }

    def _playback_visible(self) -> bool:
        vision = LocateTextTool()
        try:
            image = vision._capture_active_window()
            words = vision._extract_ocr_words(image)
        except Exception:
            return False

        for label in ("pause", "tạm dừng", "resume playback"):
            if vision._matching_boxes(words, label):
                return True
        return False

    def schema(self) -> dict:
        return {
            "name": self.name,
            "description": self.description,
            "parameters": {
                "type": "object",
                "properties": {
                    "action": {
                        "type": "string",
                        "description": "open | search | play. open mở app, search hoặc play tìm và mở bài theo query.",
                    },
                    "query": {"type": "string", "description": "Tên bài hoặc từ khóa tìm trên Spotify."},
                    "track_name": {"type": "string", "description": "Tên bài hát."},
                    "artist": {"type": "string", "description": "Tên nghệ sĩ nếu có."},
                },
                "required": [],
            },
        }

    def _find_spotify_executable(self) -> str | None:
        common_locations = [
            r"%APPDATA%\Spotify\Spotify.exe",
            r"%LOCALAPPDATA%\Spotify\Spotify.exe",
            r"%PROGRAMFILES%\Spotify\Spotify.exe",
            r"%PROGRAMFILES(X86)%\Spotify\Spotify.exe",
            r"%LOCALAPPDATA%\Microsoft\WindowsApps\Spotify.exe",
        ]

        for candidate in common_locations:
            expanded = os.path.expandvars(candidate)
            if os.path.exists(expanded):
                return expanded

        try:
            result = subprocess.run(["where", "spotify"], capture_output=True, text=True, check=False)
            if result.returncode == 0:
                for line in result.stdout.splitlines():
                    cleaned = line.strip()
                    if cleaned and os.path.exists(cleaned):
                        return cleaned
        except Exception:
            pass

        return None

    def _build_spotify_uri(self, query: str) -> str:
        encoded = quote_plus(query.strip())
        return f"spotify:search:{encoded}"

    def _process_started(self, process_name: str, timeout: float = 8.0) -> bool:
        deadline = time.time() + timeout
        while time.time() < deadline:
            try:
                result = subprocess.run(["tasklist", "/fo", "csv", "/nh"], capture_output=True, text=True, check=False)
                if result.returncode == 0:
                    lines = result.stdout.splitlines()
                    for line in lines:
                        if not line.strip():
                            continue
                        parts = [p.strip().strip('"') for p in line.split(',')]
                        if not parts:
                            continue
                        name = parts[0].lower()
                        if name == process_name.lower():
                            return True
            except Exception:
                pass
            time.sleep(0.25)
        return False
