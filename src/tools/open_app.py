import os
import subprocess
import time

from src.tools.base import Tool

# Map các app phổ biến không nằm trong PATH / App Paths của Windows.
# Value có thể là:
#   - đường dẫn tuyệt đối tới .exe (dùng %APPDATA%, %LOCALAPPDATA% qua os.path.expandvars)
#   - protocol URI (vd "spotify:")
KNOWN_APPS = {
    "spotify": [
        r"%APPDATA%\Spotify\Spotify.exe",
        r"%LOCALAPPDATA%\Spotify\Spotify.exe",
        r"%PROGRAMFILES%\Spotify\Spotify.exe",
        r"%PROGRAMFILES(X86)%\Spotify\Spotify.exe",
        r"%LOCALAPPDATA%\Microsoft\WindowsApps\Spotify.exe",
    ],
    "discord": [
        r"%LOCALAPPDATA%\Discord\Update.exe --processStart Discord.exe",
        r"%PROGRAMFILES%\Discord\Update.exe --processStart Discord.exe",
    ],
}


class OpenAppTool(Tool):
    name = "open_app"
    description = "Mở một ứng dụng trên Windows theo tên lệnh (vd: notepad, calc, chrome, spotify, discord)"

    def run(self, app_name: str) -> str:
        key = (app_name or "").strip().lower()
        if not key:
            return {"success": False, "error": "Tên app không được rỗng"}

        attempts = self._candidate_targets(key)
        last_error = None

        for target in attempts:
            expanded = os.path.expandvars(target)
            if " " in expanded and not expanded.endswith(".exe") and not expanded.endswith(":"):
                try:
                    os.startfile(expanded)
                    if self._process_started(key):
                        return {"success": True, "result": f"Đã mở {key}"}
                    last_error = RuntimeError(f"Ứng dụng {key} không xuất hiện sau khi khởi động")
                    continue
                except Exception as exc:
                    last_error = exc
                    continue

            if not os.path.exists(expanded):
                last_error = FileNotFoundError(f"Không tìm thấy ứng dụng {key} ở {expanded}")
                continue

            try:
                os.startfile(expanded)
            except Exception as exc:
                last_error = exc
                continue

            if self._process_started(key):
                return {"success": True, "result": f"Đã mở {key}"}

            last_error = RuntimeError(f"Ứng dụng {key} không xuất hiện sau khi khởi động")

        if last_error:
            return {"success": False, "error": f"Không mở được {app_name}: {last_error}"}
        return {"success": False, "error": f"Không mở được {app_name}"}

    def _candidate_targets(self, key: str):
        known = KNOWN_APPS.get(key, [])
        candidates = list(known)
        if key not in {"spotify", "discord"}:
            candidates.append(key)

        env_candidates = [
            os.environ.get("PROGRAMFILES", ""),
            os.environ.get("PROGRAMFILES(X86)", ""),
            os.environ.get("LOCALAPPDATA", ""),
            os.environ.get("APPDATA", ""),
        ]

        for base_dir in env_candidates:
            if not base_dir:
                continue
            path = os.path.join(base_dir, f"{key}.exe")
            if path not in candidates:
                candidates.append(path)

        deduped = []
        seen = set()
        for item in candidates:
            if not item:
                continue
            key_item = str(item).lower()
            if key_item not in seen:
                deduped.append(item)
                seen.add(key_item)
        return deduped

    def _process_started(self, app_key: str, timeout: float = 8.0) -> bool:
        executable_names = set()
        executable_names.add(f"{app_key}.exe")
        executable_names.add(app_key)

        if app_key in {"spotify", "discord", "chrome", "notepad", "calc", "calculator", "code", "vscode"}:
            executable_names.update({
                "spotify.exe",
                "discord.exe",
                "chrome.exe",
                "notepad.exe",
                "calc.exe",
                "calculator.exe",
                "code.exe",
                "vscode.exe",
            })

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
                        if not parts or len(parts) < 2:
                            continue
                        process_name = parts[0].lower()
                        if process_name in {name.lower() for name in executable_names}:
                            return True
            except Exception:
                pass
            time.sleep(0.25)
        return False

    def schema(self) -> dict:
        return {
            "name": self.name,
            "description": self.description,
            "parameters": {
                "type": "object",
                "properties": {
                    "app_name": {
                        "type": "string",
                        "description": "Tên app cần mở, vd: notepad, spotify, discord",
                    }
                },
                "required": ["app_name"],
            },
        }