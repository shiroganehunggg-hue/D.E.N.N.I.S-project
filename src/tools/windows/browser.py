import concurrent.futures
import hashlib
import json
import logging
import os
import re
import shutil
import subprocess
import time
import unicodedata
import urllib.request
from typing import Any, Dict, List, Optional
from urllib.parse import quote_plus

from playwright.sync_api import BrowserContext, Page, Playwright, sync_playwright

from src.tools.base import Tool

logger = logging.getLogger(__name__)

DEFAULT_CHROME_PROFILE = "Profile 32"

# Playwright (sync API) chỉ được dùng trong ĐÚNG MỘT thread suốt vòng đời
# của Playwright/BrowserContext/Page — không được gọi từ thread khác,
# kể cả khi thread tạo ra nó đã kết thúc. Nhưng gui.py tạo một
# threading.Thread MỚI cho MỖI tin nhắn gửi lên (_ask_dennis), nên nếu để
# Playwright chạy trực tiếp trên thread gọi vào BrowserTool.run(), lần
# gọi tool ở tin nhắn sau (thread khác, thread cũ đã exit) sẽ dính lỗi
# "cannot switch to a different thread (which happens to have exited)".
# Giải pháp: dồn TOÀN BỘ thao tác Playwright thật vào một
# ThreadPoolExecutor(max_workers=1) singleton — executor này chỉ có đúng
# 1 worker thread, sống suốt vòng đời process, nên Playwright luôn được
# gọi từ cùng một thread bất kể request đến từ GUI thread nào.
_BROWSER_EXECUTOR: Optional[concurrent.futures.ThreadPoolExecutor] = None


def _get_browser_executor() -> concurrent.futures.ThreadPoolExecutor:
    global _BROWSER_EXECUTOR
    if _BROWSER_EXECUTOR is None:
        _BROWSER_EXECUTOR = concurrent.futures.ThreadPoolExecutor(
            max_workers=1, thread_name_prefix="dennis-browser"
        )
    return _BROWSER_EXECUTOR

CHROME_ACTIONS = {
    "launch_browser",
    "open_url",
    "new_tab",
    "close_tab",
    "switch_tab",
    "list_tabs",
    "refresh",
    "back",
    "forward",
    "get_page_text",
    "search_google",
}

# File cấu hình ánh xạ tên gọi thân thiện (vd "công việc", "cá nhân") sang
# tên thư mục profile thật của Chrome (vd "Profile 15", "Profile 32").
# Xem hướng dẫn tìm tên thư mục thật trong chính file config này.
PROFILE_CONFIG_PATH = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
    "config",
    "chrome_profiles.json",
)

_RAW_PROFILE_DIR_PATTERN = re.compile(r"^(default|profile\s*\d+)$", re.IGNORECASE)

# Cache kết nối theo profile trong suốt vòng đời tiến trình gui.py, để không
# phải mở lại Chrome / kết nối lại CDP cho mỗi lệnh gọi tool.
# profile -> {"port": int, "playwright": Playwright, "browser": Browser,
#             "context": BrowserContext, "current_page": Page}
_CONNECTIONS: Dict[str, Dict[str, Any]] = {}
_PLAYWRIGHT_SINGLETON: Optional[Playwright] = None


def _strip_accents(text: str) -> str:
    normalized = unicodedata.normalize("NFD", text)
    return "".join(ch for ch in normalized if unicodedata.category(ch) != "Mn")


def _normalize_alias_key(text: str) -> str:
    return _strip_accents(str(text)).strip().lower()


def _get_playwright() -> Playwright:
    global _PLAYWRIGHT_SINGLETON
    if _PLAYWRIGHT_SINGLETON is None:
        _PLAYWRIGHT_SINGLETON = sync_playwright().start()
    return _PLAYWRIGHT_SINGLETON


def _pick_port_for_profile(profile: str) -> int:
    """Cổng CDP cố định (deterministic) theo từng profile, không phụ thuộc
    PYTHONHASHSEED, để lần chạy sau vẫn đoán đúng cổng đã dùng lần trước."""
    digest = int(hashlib.sha256(profile.encode("utf-8")).hexdigest(), 16) % 5000
    return 40000 + digest


def _wait_for_cdp(port: int, timeout: float) -> bool:
    deadline = time.time() + timeout
    url = f"http://127.0.0.1:{port}/json/version"
    while time.time() < deadline:
        try:
            with urllib.request.urlopen(url, timeout=1) as resp:
                if resp.status == 200:
                    return True
        except Exception:
            pass
        time.sleep(0.3)
    return False


class BrowserTool(Tool):
    """Điều khiển Google Chrome qua Chrome DevTools Protocol (Playwright).

    So với bản cũ (giả lập phím Ctrl+T/Ctrl+L/Enter), bản này:
    - Mở tab / điều hướng bằng API thật, không phụ thuộc cửa sổ nào đang focus.
    - Biết chắc trang đã load xong (domcontentloaded), không cần sleep() đoán mò.
    - Đọc được nội dung text thật của trang (get_page_text, search_google) -
      nền tảng để DENNIS tự thu thập thông tin, thay vì chỉ gõ phím mù.
    """

    name = "browser"
    description = (
        "Điều khiển Google Chrome qua CDP: mở/chuyển/đóng tab, điều hướng, "
        "đọc nội dung trang, tìm kiếm Google và lấy kết quả dạng text. Hỗ trợ chọn profile theo tên."
    )

    def run(
        self,
        action: str,
        url: str = "",
        profile: str = "",
        query: str = "",
        tab_index: Optional[int] = None,
    ) -> dict:
        # Không chạy Playwright trực tiếp trên thread gọi vào đây (xem
        # giải thích ở _get_browser_executor phía trên file) — luôn đẩy
        # qua thread nền cố định duy nhất rồi đợi kết quả.
        executor = _get_browser_executor()
        future = executor.submit(
            self._run_impl, action, url, profile, query, tab_index
        )
        try:
            return future.result(timeout=30)
        except concurrent.futures.TimeoutError:
            resolved_profile = self._resolve_profile_name(profile)
            return self._err(
                "Thao tác Chrome quá lâu, đã timeout sau 30 giây",
                resolved_profile,
            )

    def _run_impl(
        self,
        action: str,
        url: str = "",
        profile: str = "",
        query: str = "",
        tab_index: Optional[int] = None,
    ) -> dict:
        resolved_profile = self._resolve_profile_name(profile)
        try:
            if not action or action not in CHROME_ACTIONS:
                raise ValueError(f"Unsupported browser action: {action}")

            context = self._get_context(resolved_profile)

            if action == "launch_browser":
                page = self._current_page(resolved_profile, context)
                page.bring_to_front()
                return self._ok("Chrome sẵn sàng", resolved_profile, page)

            if action == "open_url":
                if not url or not str(url).strip():
                    return self._err("url không được rỗng", resolved_profile)
                page = self._current_page(resolved_profile, context)
                page.goto(url, wait_until="domcontentloaded", timeout=15000)
                page.bring_to_front()
                return self._ok(f"Đã mở {url}", resolved_profile, page)

            if action == "new_tab":
                page = context.new_page()
                if url and str(url).strip():
                    page.goto(url, wait_until="domcontentloaded", timeout=15000)
                self._set_current_page(resolved_profile, page)
                page.bring_to_front()
                return self._ok("Đã mở tab mới", resolved_profile, page)

            if action == "close_tab":
                page = self._current_page(resolved_profile, context)
                page.close()
                remaining = context.pages
                if remaining:
                    self._set_current_page(resolved_profile, remaining[-1])
                    remaining[-1].bring_to_front()
                    return self._ok("Đã đóng tab", resolved_profile, remaining[-1])
                return {"success": True, "result": "Đã đóng tab (không còn tab nào)", "data": {"profile": resolved_profile}, "error": None}

            if action == "switch_tab":
                pages = context.pages
                idx = 0 if tab_index is None else int(tab_index)
                if idx < 0 or idx >= len(pages):
                    return self._err(f"tab_index {idx} không hợp lệ (có {len(pages)} tab)", resolved_profile)
                page = pages[idx]
                page.bring_to_front()
                self._set_current_page(resolved_profile, page)
                return self._ok(f"Đã chuyển sang tab {idx}", resolved_profile, page)

            if action == "list_tabs":
                pages = context.pages
                tabs = [{"index": i, "title": p.title(), "url": p.url} for i, p in enumerate(pages)]
                return {"success": True, "result": f"{len(tabs)} tab đang mở", "data": {"profile": resolved_profile, "tabs": tabs}, "error": None}

            if action in ("back", "forward", "refresh"):
                page = self._current_page(resolved_profile, context)
                if action == "back":
                    page.go_back(wait_until="domcontentloaded", timeout=15000)
                elif action == "forward":
                    page.go_forward(wait_until="domcontentloaded", timeout=15000)
                else:
                    page.reload(wait_until="domcontentloaded", timeout=15000)
                page.bring_to_front()
                return self._ok(f"Đã {action}", resolved_profile, page)

            if action == "get_page_text":
                page = self._current_page(resolved_profile, context)
                text = self._extract_visible_text(page)
                return {
                    "success": True,
                    "result": text,
                    "data": {"profile": resolved_profile, "url": page.url, "title": page.title(), "length": len(text)},
                    "error": None,
                }

            if action == "search_google":
                if not query or not str(query).strip():
                    return self._err("query không được rỗng", resolved_profile)
                page = self._current_page(resolved_profile, context)
                target_url = f"https://www.google.com/search?q={quote_plus(query)}"
                page.goto(target_url, wait_until="domcontentloaded", timeout=15000)
                page.bring_to_front()
                page.wait_for_timeout(500)
                text = self._extract_visible_text(page)
                return {
                    "success": True,
                    "result": text,
                    "data": {"profile": resolved_profile, "query": query, "url": page.url, "length": len(text)},
                    "error": None,
                }

            return self._err("Unsupported browser action", resolved_profile)
        except Exception as exc:
            logger.exception("[BROWSER] operation failed: %s", exc)
            return {
                "success": False,
                "result": "",
                "data": {"action": action, "url": url, "profile": resolved_profile, "query": query},
                "error": str(exc),
            }

    def schema(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "description": self.description,
            "parameters": {
                "type": "object",
                "properties": {
                    "action": {
                        "type": "string",
                        "description": (
                            "Một trong: launch_browser, open_url, new_tab, close_tab, switch_tab, "
                            "list_tabs, refresh, back, forward, get_page_text, search_google"
                        ),
                    },
                    "url": {"type": "string", "description": "URL cần mở khi action là open_url hoặc new_tab"},
                    "profile": {
                        "type": "string",
                        "description": (
                            "Tên profile Chrome muốn dùng, đúng như người dùng nói (vd 'công việc', 'cá nhân'). "
                            "Bỏ trống để dùng profile mặc định."
                        ),
                    },
                    "query": {"type": "string", "description": "Từ khoá cần tìm khi action là search_google"},
                    "tab_index": {"type": "integer", "description": "Số thứ tự tab (bắt đầu từ 0) khi action là switch_tab"},
                },
                "required": ["action"],
            },
        }

    # ---------- Helpers: kết quả trả về ----------

    def _ok(self, message: str, profile: str, page: Page) -> dict:
        return {
            "success": True,
            "result": message,
            "data": {"profile": profile, "url": page.url, "title": page.title()},
            "error": None,
        }

    def _err(self, message: str, profile: str) -> dict:
        return {"success": False, "result": "", "data": {"profile": profile}, "error": message}

    def _extract_visible_text(self, page: Page, max_chars: int = 4000) -> str:
        try:
            text = page.inner_text("body")
        except Exception:
            text = ""
        text = " ".join(text.split())
        return text[:max_chars]

    # ---------- Profile resolution (giữ nguyên logic alias) ----------

    def _load_profile_config(self) -> Dict[str, Any]:
        try:
            with open(PROFILE_CONFIG_PATH, "r", encoding="utf-8") as fh:
                data = json.load(fh)
            if isinstance(data, dict):
                return data
        except FileNotFoundError:
            logger.warning("[BROWSER] Không tìm thấy config profile tại %s, dùng mặc định %s", PROFILE_CONFIG_PATH, DEFAULT_CHROME_PROFILE)
        except Exception:
            logger.exception("[BROWSER] Lỗi đọc config profile, dùng mặc định %s", DEFAULT_CHROME_PROFILE)
        return {"default_profile": DEFAULT_CHROME_PROFILE, "aliases": {}}

    def _resolve_profile_name(self, requested: str) -> str:
        config = self._load_profile_config()
        default_profile = str(config.get("default_profile") or DEFAULT_CHROME_PROFILE)

        requested = (requested or "").strip()
        if not requested:
            return default_profile

        if _RAW_PROFILE_DIR_PATTERN.match(requested):
            return requested

        aliases = config.get("aliases") or {}
        normalized_requested = _normalize_alias_key(requested)
        for alias_name, real_profile in aliases.items():
            if _normalize_alias_key(alias_name) == normalized_requested:
                return str(real_profile)

        logger.warning(
            "[BROWSER] Không tìm thấy alias profile '%s' trong %s, dùng profile mặc định %s.",
            requested, PROFILE_CONFIG_PATH, default_profile,
        )
        return default_profile

    # ---------- Kết nối CDP ----------

    def _get_chrome_path(self) -> Optional[str]:
        candidates = [
            r"C:\Program Files\Google\Chrome\Application\chrome.exe",
            r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
        ]
        for path in candidates:
            if os.path.exists(path):
                return path
        return shutil.which("chrome.exe")

    def _find_running_profile_process(self, profile: str) -> Optional[int]:
        try:
            result = subprocess.run(
                [
                    "powershell",
                    "-NoProfile",
                    "-Command",
                    "Get-CimInstance Win32_Process -Filter \"Name='chrome.exe'\" "
                    "| ForEach-Object { \"$($_.ProcessId)|$($_.CommandLine)\" }",
                ],
                capture_output=True,
                text=True,
                check=False,
            )
            if result.returncode != 0:
                return None
            target_profile = f"--profile-directory={profile}".lower()
            dennis_user_data_dir = self._get_chrome_user_data_dir()
            target_user_data = f"--user-data-dir={dennis_user_data_dir}".lower() if dennis_user_data_dir else None
            for raw_line in result.stdout.splitlines():
                line = str(raw_line).strip()
                if not line or "|" not in line:
                    continue
                pid_text, _, cmdline = line.partition("|")
                normalized = cmdline.lower().replace('"', "")
                # Phải khớp cả profile-directory LẪN user-data-dir của DENNIS,
                # để không nhầm với cửa sổ Chrome bình thường của bạn dùng
                # trùng tên profile (vd cùng là "Profile 32" nhưng ở User Data thật).
                if target_profile in normalized and (target_user_data is None or target_user_data in normalized):
                    try:
                        return int(pid_text.strip())
                    except ValueError:
                        continue
        except Exception:
            return None
        return None

    def _get_chrome_user_data_dir(self) -> Optional[str]:
        # Chrome (từ ~bản 111) từ chối mở cổng --remote-debugging-port nếu
        # không kèm --user-data-dir tường minh, kể cả khi dùng đúng thư mục
        # mặc định thật. Không truyền cờ này thì Chrome vẫn mở bình thường
        # nhưng lặng lẽ không bật cổng debug -> CDP không bao giờ kết nối được.
        #
        # QUAN TRỌNG: KHÔNG trỏ vào User Data thật của Chrome (nơi bạn tự
        # dùng hàng ngày). Chrome chỉ mở cổng debug khi nó khởi động một
        # TIẾN TRÌNH MỚI cho đúng user-data-dir đó; nếu Chrome với user-data-dir
        # thật đã đang chạy sẵn (kể cả do bạn tự mở tay), lệnh launch mới của
        # DENNIS sẽ chỉ mở thêm cửa sổ trong tiến trình cũ và Chrome sẽ ÂM
        # THẦM bỏ qua cờ debug -> phải taskkill hết Chrome thì DENNIS mới
        # dùng được. Dùng một user-data-dir RIÊNG cho DENNIS giải quyết việc
        # này triệt để: đây luôn là tiến trình Chrome độc lập, không đụng
        # tới (và không cần tắt) cửa sổ Chrome bình thường bạn đang dùng.
        local_appdata = os.environ.get("LOCALAPPDATA")
        if not local_appdata:
            return None
        path = os.path.join(local_appdata, "DENNIS", "ChromeProfile")
        os.makedirs(path, exist_ok=True)
        return path

    def _get_context(self, profile: str) -> BrowserContext:
        cached = _CONNECTIONS.get(profile)
        if cached:
            try:
                if cached["browser"].is_connected():
                    return cached["context"]
            except Exception:
                pass
            _CONNECTIONS.pop(profile, None)

        port = _pick_port_for_profile(profile)
        existing_pid = self._find_running_profile_process(profile)

        if not existing_pid:
            chrome_path = self._get_chrome_path()
            if not chrome_path:
                raise RuntimeError("Không tìm thấy chrome.exe trên máy")
            user_data_dir = self._get_chrome_user_data_dir()
            launch_args = [chrome_path, f"--profile-directory={profile}", "--new-window", f"--remote-debugging-port={port}"]
            if user_data_dir:
                launch_args.append(f"--user-data-dir={user_data_dir}")
            else:
                logger.warning(
                    "[BROWSER] Không xác định được thư mục User Data (%%LOCALAPPDATA%% trống?), "
                    "Chrome có thể từ chối bật cổng debug."
                )
            subprocess.Popen(launch_args, shell=False)
            logger.info("[BROWSER] Launched chrome profile=%s port=%s user_data_dir=%s", profile, port, user_data_dir)
            if not _wait_for_cdp(port, timeout=10.0):
                raise RuntimeError(
                    f"Chrome (profile {profile}) không mở được cổng debug sau 10s. Thử lại hoặc kiểm tra chrome.exe."
                )
        else:
            # Chrome cho profile này đã chạy sẵn. Chỉ kết nối được qua CDP nếu
            # NÓ được DENNIS tự khởi động từ đầu với --remote-debugging-port
            # (Chrome chỉ nhận cờ này khi khởi tạo tiến trình mới; một cửa sổ
            # đã mở từ trước, kể cả do người dùng tự mở tay, sẽ không tự bật
            # debug port dù ta cố truyền cờ ở lần gọi sau).
            if not _wait_for_cdp(port, timeout=1.5):
                raise RuntimeError(
                    f"Chrome (profile {profile}) đang chạy nhưng KHÔNG ở chế độ debug nên DENNIS không thể đọc/điều "
                    f"khiển qua CDP. Hãy đóng hết cửa sổ Chrome của profile này (Task Manager hoặc "
                    f"'taskkill /F /IM chrome.exe /T') rồi thử lại để DENNIS tự mở lại đúng chế độ."
                )

        pw = _get_playwright()
        browser = pw.chromium.connect_over_cdp(f"http://127.0.0.1:{port}")
        context = browser.contexts[0] if browser.contexts else browser.new_context()
        _CONNECTIONS[profile] = {"port": port, "browser": browser, "context": context, "current_page": None}
        return context

    def _current_page(self, profile: str, context: BrowserContext) -> Page:
        cached = _CONNECTIONS.setdefault(profile, {})
        page = cached.get("current_page")
        if page is not None:
            try:
                _ = page.url
                return page
            except Exception:
                pass
        pages = context.pages
        page = pages[-1] if pages else context.new_page()
        cached["current_page"] = page
        return page

    def _set_current_page(self, profile: str, page: Page) -> None:
        _CONNECTIONS.setdefault(profile, {})["current_page"] = page