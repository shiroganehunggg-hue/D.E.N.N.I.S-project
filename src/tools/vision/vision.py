import logging
import os
import time
from typing import Any, Dict, List, Optional

from PIL import Image, ImageGrab

try:
    import pyautogui  # type: ignore
except Exception:  # pragma: no cover - optional ergonomic dependency
    pyautogui = None

try:
    import pytesseract  # type: ignore
except Exception:  # pragma: no cover - optional OCR dependency
    pytesseract = None

try:
    import win32gui  # type: ignore
except Exception:  # pragma: no cover - Windows-only helper
    win32gui = None

from src.tools.base import Tool

logger = logging.getLogger(__name__)

_CACHE: Dict[str, Dict[str, Any]] = {}
_CACHE_TTL_SECONDS = 2.0


def _configure_tesseract_executable() -> Optional[str]:
    """Ensure pytesseract points to a valid Windows Tesseract install when present."""
    if pytesseract is None:
        return None

    pytesseract_module = getattr(pytesseract, "pytesseract", None)
    if pytesseract_module is None:
        return None

    current = getattr(pytesseract_module, "tesseract_cmd", None)
    if current:
        current_str = str(current)
        if os.path.exists(current_str):
            return current_str

    env_value = os.environ.get("TESSERACT_PATH") or os.environ.get("TESSERACT_CMD")
    if env_value and os.path.exists(env_value):
        pytesseract_module.tesseract_cmd = env_value
        return env_value

    if os.name != "nt":
        if current:
            return str(current)
        return None

    candidates = [
        r"C:\Program Files\Tesseract-OCR\tesseract.exe",
        r"C:\Program Files (x86)\Tesseract-OCR\tesseract.exe",
        os.path.join(os.environ.get("LOCALAPPDATA", ""), "Programs", "Tesseract-OCR", "tesseract.exe"),
        os.path.join(os.environ.get("USERPROFILE", ""), "AppData", "Local", "Programs", "Tesseract-OCR", "tesseract.exe"),
    ]

    for candidate in candidates:
        if candidate and os.path.exists(candidate):
            pytesseract_module.tesseract_cmd = candidate
            return candidate

    if current:
        pytesseract_module.tesseract_cmd = str(current)
        return str(current)

    return None


class VisionResult(dict):
    """Structured result object used by vision tools."""

    def __init__(
        self,
        text: str = "",
        bounding_boxes: Optional[List[Dict[str, Any]]] = None,
        icons: Optional[List[Dict[str, Any]]] = None,
        buttons: Optional[List[Dict[str, Any]]] = None,
        success: bool = True,
    ):
        super().__init__(
            success=success,
            text=text or "",
            bounding_boxes=bounding_boxes or [],
            icons=icons or [],
            buttons=buttons or [],
        )


class _VisionMixin:
    """Shared utilities for desktop vision tools."""

    def _capture_desktop(self) -> Image.Image:
        return ImageGrab.grab()

    def _capture_active_window(self) -> Image.Image:
        if win32gui is None:
            return self._capture_desktop()

        hwnd = win32gui.GetForegroundWindow()
        left, top, right, bottom = win32gui.GetWindowRect(hwnd)
        return ImageGrab.grab(bbox=(left, top, right, bottom))

    def _save_image(self, image: Image.Image, prefix: str = "desktop") -> str:
        os.makedirs(os.path.join(os.getcwd(), "memory", "screenshots"), exist_ok=True)
        path = os.path.join(os.getcwd(), "memory", "screenshots", f"{prefix}_{int(time.time() * 1000)}.png")
        image.save(path)
        return path

    def _safe_region_list(self, image: Image.Image, size_hint: int, label: str) -> List[Dict[str, Any]]:
        width, height = image.size
        step_x = max(1, width // max(3, size_hint))
        step_y = max(1, height // max(3, size_hint))
        regions: List[Dict[str, Any]] = []
        for y in range(0, height, step_y):
            for x in range(0, width, step_x):
                x2 = min(width, x + step_x)
                y2 = min(height, y + step_y)
                crop = image.crop((x, y, x2, y2)).convert("L")
                pixels = list(crop.getdata())
                if not pixels:
                    continue
                mean = sum(pixels) / len(pixels)
                variance = sum((p - mean) ** 2 for p in pixels) / len(pixels)
                if variance > 2500:
                    regions.append({"x": x, "y": y, "width": max(1, x2 - x), "height": max(1, y2 - y), "label": label})
                    if len(regions) >= 12:
                        return regions
        return regions or [{"x": 0, "y": 0, "width": max(1, width), "height": max(1, height), "label": label}]

    def _extract_text_simple(self, image: Any) -> str:
        return " ".join(word["text"] for word in self._extract_ocr_words(image))

    def _extract_ocr_words(self, image: Any) -> List[Dict[str, Any]]:
        """Return valid word-level Tesseract detections with layout metadata."""
        if pytesseract is None:
            raise RuntimeError("OCR backend is unavailable: pytesseract is not installed.")

        _configure_tesseract_executable()

        try:
            data = pytesseract.image_to_data(image, output_type=pytesseract.Output.DICT)
        except Exception as exc:  # pragma: no cover - OCR backend availability
            logger.warning("OCR backend failed: %s", exc)
            raise RuntimeError(f"OCR backend failed: {exc}") from exc

        words: List[Dict[str, Any]] = []
        texts = data.get("text", [])
        for index, raw_text in enumerate(texts):
            text = str(raw_text).strip()
            if not text:
                continue
            try:
                confidence = float(data["conf"][index])
                x = int(data["left"][index])
                y = int(data["top"][index])
                width = int(data["width"][index])
                height = int(data["height"][index])
            except (KeyError, IndexError, TypeError, ValueError):
                continue

            # Tesseract emits -1 for hierarchy entries, not valid text words.
            if confidence < 0 or width <= 0 or height <= 0:
                continue
            words.append(
                {
                    "text": text,
                    "x": x,
                    "y": y,
                    "width": width,
                    "height": height,
                    "confidence": confidence / 100.0,
                    "block_num": data.get("block_num", [None] * len(texts))[index] if index < len(data.get("block_num", [])) else None,
                    "par_num": data.get("par_num", [None] * len(texts))[index] if index < len(data.get("par_num", [])) else None,
                    "line_num": data.get("line_num", [None] * len(texts))[index] if index < len(data.get("line_num", [])) else None,
                }
            )
        return words

    @staticmethod
    def _public_box(word: Dict[str, Any]) -> Dict[str, Any]:
        return {key: word[key] for key in ("text", "x", "y", "width", "height", "confidence")}

    @staticmethod
    def _normalise_text(text: str) -> str:
        return " ".join(str(text).casefold().split())

    @staticmethod
    def _combined_box(words: List[Dict[str, Any]]) -> Dict[str, Any]:
        left = min(word["x"] for word in words)
        top = min(word["y"] for word in words)
        right = max(word["x"] + word["width"] for word in words)
        bottom = max(word["y"] + word["height"] for word in words)
        return {
            "text": " ".join(word["text"] for word in words),
            "x": left,
            "y": top,
            "width": right - left,
            "height": bottom - top,
            "confidence": sum(word["confidence"] for word in words) / len(words),
        }

    @staticmethod
    def _words_are_nearby(left: Dict[str, Any], right: Dict[str, Any]) -> bool:
        horizontal_gap = right["x"] - (left["x"] + left["width"])
        max_gap = max(40, 3 * max(left["height"], right["height"]))
        return horizontal_gap <= max_gap

    def _matching_boxes(self, words: List[Dict[str, Any]], query: str) -> List[Dict[str, Any]]:
        """Find word or same-line phrase boxes without crossing UI regions."""
        normalised_query = self._normalise_text(query)
        matches: List[Dict[str, Any]] = []
        seen = set()

        def add_match(box: Dict[str, Any]) -> None:
            candidate = self._normalise_text(box["text"])
            if normalised_query not in candidate:
                return
            signature = (box["x"], box["y"], box["width"], box["height"], candidate)
            if signature not in seen:
                seen.add(signature)
                matches.append(box)

        for word in words:
            add_match(self._public_box(word))

        lines: Dict[tuple, List[Dict[str, Any]]] = {}
        for word in words:
            line_key = (word["block_num"], word["par_num"], word["line_num"])
            if any(part is None for part in line_key):
                continue
            lines.setdefault(line_key, []).append(word)

        for line_words in lines.values():
            ordered_words = sorted(line_words, key=lambda word: word["x"])
            for start in range(len(ordered_words)):
                phrase = [ordered_words[start]]
                for next_word in ordered_words[start + 1 :]:
                    if not self._words_are_nearby(phrase[-1], next_word):
                        break
                    phrase.append(next_word)
                    add_match(self._combined_box(phrase))
        return matches


class TakeDesktopScreenshotTool(_VisionMixin, Tool):
    """Save a screenshot of the full desktop locally."""

    name = "take_desktop_screenshot"
    description = "Lưu ảnh chụp toàn bộ màn hình desktop vào bộ nhớ cục bộ"

    def run(self) -> dict:
        try:
            image = self._capture_desktop()
            path = self._save_image(image, "desktop")
            return {
                "success": True,
                "size": image.size,
                "mode": image.mode,
                "path": path,
                "timestamp": int(time.time()),
            }
        except Exception as exc:
            logger.exception("Failed to capture desktop screenshot: %s", exc)
            return {"success": False, "error": str(exc)}

    def schema(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "description": self.description,
            "parameters": {"type": "object", "properties": {}, "required": []},
        }

    def _cache_key(self, prefix: str) -> str:
        return f"{prefix}:{int(time.time() // _CACHE_TTL_SECONDS)}"


class OcrScreenTool(_VisionMixin, Tool):
    """Extract visible text from the current desktop image."""

    name = "ocr_screen"
    description = "Trích xuất văn bản từ màn hình hiện tại"

    def run(self) -> dict:
        try:
            image = self._capture_desktop()
            words = self._extract_ocr_words(image)
            text = " ".join(word["text"] for word in words)
            boxes = [self._public_box(word) for word in words]
            return VisionResult(text=text, bounding_boxes=boxes)
        except Exception as exc:
            logger.exception("Failed to OCR screen: %s", exc)
            return {"success": False, "error": str(exc)}

    def schema(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "description": self.description,
            "parameters": {"type": "object", "properties": {}, "required": []},
        }


class DetectIconsTool(_VisionMixin, Tool):
    """Placeholder for icon detection, which is not implemented."""

    enabled = False
    name = "detect_icons"
    description = "Nhận diện icon chưa được hỗ trợ"

    def run(self) -> dict:
        return {"success": False, "error": "Icon detection is not implemented yet."}

    def schema(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "description": self.description,
            "parameters": {"type": "object", "properties": {}, "required": []},
        }


class DetectButtonsTool(_VisionMixin, Tool):
    """Placeholder for button detection, which is not implemented."""

    enabled = False
    name = "detect_buttons"
    description = "Nhận diện nút bấm chưa được hỗ trợ"

    def run(self) -> dict:
        return {"success": False, "error": "Button detection is not implemented yet."}

    def schema(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "description": self.description,
            "parameters": {"type": "object", "properties": {}, "required": []},
        }


class DetectTextRegionsTool(_VisionMixin, Tool):
    """Placeholder for text-region detection, which is not implemented."""

    enabled = False
    name = "detect_text_regions"
    description = "Phân vùng chữ trên màn hình chưa được hỗ trợ; dùng OCR"

    def run(self) -> dict:
        return {"success": False, "error": "Text-region detection is not implemented; use OCR instead."}

    def schema(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "description": self.description,
            "parameters": {"type": "object", "properties": {}, "required": []},
        }


class GetActiveWindowScreenshotTool(_VisionMixin, Tool):
    """Capture the current active window as a screenshot."""

    name = "get_active_window_screenshot"
    description = "Chụp ảnh cửa sổ đang active"

    def run(self) -> dict:
        try:
            image = self._capture_active_window()
            path = self._save_image(image, "active_window")
            return {"success": True, "size": image.size, "mode": image.mode, "path": path}
        except Exception as exc:
            logger.exception("Failed to capture active window screenshot: %s", exc)
            return {"success": False, "error": str(exc)}

    def schema(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "description": self.description,
            "parameters": {"type": "object", "properties": {}, "required": []},
        }


class LocateTextTool(_VisionMixin, Tool):
    """Locate a text snippet in the current screen by simple matching."""

    name = "locate_text"
    description = "Tìm vị trí của một đoạn text trên màn hình"

    def run(self, text: str) -> dict:
        try:
            if not text or not str(text).strip():
                raise ValueError("text không được rỗng")
            image = self._capture_desktop()
            query = str(text).strip()
            matches = self._matching_boxes(self._extract_ocr_words(image), query)
            result = VisionResult(text=query, bounding_boxes=matches)
            result["found"] = bool(matches)
            if not matches:
                result["message"] = f"Text '{query}' was not found in the image."
            return result
        except Exception as exc:
            logger.exception("Failed to locate text: %s", exc)
            return {"success": False, "error": str(exc)}

    def schema(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "description": self.description,
            "parameters": {
                "type": "object",
                "properties": {"text": {"type": "string", "description": "Đoạn văn bản cần tìm"}},
                "required": ["text"],
            },
        }


class LocateIconTool(_VisionMixin, Tool):
    """Report that icon localization is not available yet."""

    enabled = False
    name = "locate_icon"
    description = "Nhận diện vị trí biểu tượng chưa được hỗ trợ"

    def run(self, description: str) -> dict:
        try:
            if not description or not str(description).strip():
                raise ValueError("description không được rỗng")
            return {"success": False, "error": "Icon localization is not implemented yet."}
        except Exception as exc:
            logger.exception("Failed to locate icon: %s", exc)
            return {"success": False, "error": str(exc)}

    def schema(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "description": self.description,
            "parameters": {
                "type": "object",
                "properties": {"description": {"type": "string", "description": "Mô tả biểu tượng cần tìm"}},
                "required": ["description"],
            },
        }
