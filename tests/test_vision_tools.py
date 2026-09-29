from unittest.mock import patch

import pytest

from PIL import Image

from src.tools.registry import discover_tools
from src.tools.vision.vision import (
    DetectButtonsTool,
    DetectIconsTool,
    DetectTextRegionsTool,
    LocateIconTool,
    LocateTextTool,
    OcrScreenTool,
)


def _ocr_data(words):
    fields = {key: [] for key in ("text", "conf", "left", "top", "width", "height", "block_num", "par_num", "line_num")}
    for word in words:
        fields["text"].append(word["text"])
        fields["conf"].append(str(word.get("conf", 90)))
        fields["left"].append(word["x"])
        fields["top"].append(word["y"])
        fields["width"].append(word["width"])
        fields["height"].append(word["height"])
        fields["block_num"].append(word.get("block_num", 1))
        fields["par_num"].append(word.get("par_num", 1))
        fields["line_num"].append(word.get("line_num", 1))
    return fields


def _run_locate(query, words):
    tool = LocateTextTool()
    image = Image.new("RGB", (400, 300), "white")
    with patch.object(tool, "_capture_desktop", return_value=image), patch("src.tools.vision.vision.pytesseract.image_to_data", return_value=_ocr_data(words)):
        return tool.run(query)


def test_vision_tools_are_discovered():
    tools = discover_tools()
    names = {tool.name for tool in tools}

    assert "take_desktop_screenshot" in names
    assert "ocr_screen" in names
    assert "detect_icons" not in names
    assert "detect_buttons" not in names
    assert "detect_text_regions" not in names
    assert "get_active_window_screenshot" in names
    assert "locate_text" in names
    assert "locate_icon" not in names


def test_visible_text_tools_describe_screen_ocr_intent():
    tools = {tool.name: tool for tool in discover_tools()}

    assert "màn hình" in tools["locate_text"].description
    assert "màn hình" in tools["ocr_screen"].description


def test_locate_icon_reports_unsupported_instead_of_fake_coordinates():
    result = LocateIconTool().run("settings gear")

    assert result["success"] is False
    assert "not implemented" in result["error"]


@pytest.mark.parametrize(
    "tool_class",
    [DetectIconsTool, DetectButtonsTool, DetectTextRegionsTool],
)
def test_placeholder_vision_tools_report_unsupported(tool_class):
    result = tool_class().run()

    assert result["success"] is False
    assert "not implemented" in result["error"]


def test_windows_tesseract_path_is_auto_configured():
    import src.tools.vision.vision as vision_module

    fake_pytesseract_module = type("FakePytesseractModule", (), {"tesseract_cmd": "tesseract"})()
    fake_pytesseract = type("FakePyTesseract", (), {"pytesseract": fake_pytesseract_module})()
    fake_path = r"C:\Program Files\Tesseract-OCR\tesseract.exe"

    with patch.object(vision_module, "pytesseract", fake_pytesseract), patch.object(vision_module.os, "name", "nt"), patch.object(vision_module.os.path, "exists", side_effect=lambda p: p == fake_path), patch.dict(vision_module.os.environ, {}, clear=True):
        configured = vision_module._configure_tesseract_executable()

    assert configured == fake_path
    assert fake_pytesseract_module.tesseract_cmd == fake_path


def test_locate_text_exact_match_returns_tesseract_bbox():
    result = _run_locate("Search", [{"text": "Search", "x": 12, "y": 34, "width": 80, "height": 20, "conf": 96}])

    assert result["found"] is True
    assert result["bounding_boxes"] == [{"text": "Search", "x": 12, "y": 34, "width": 80, "height": 20, "confidence": 0.96}]


def test_locate_text_is_case_insensitive():
    result = _run_locate("search", [{"text": "SEARCH", "x": 20, "y": 40, "width": 90, "height": 25, "conf": 91}])

    assert result["found"] is True
    assert result["bounding_boxes"][0]["x"] == 20
    assert result["bounding_boxes"][0]["y"] == 40
    assert result["bounding_boxes"][0]["width"] == 90
    assert result["bounding_boxes"][0]["height"] == 25


def test_locate_text_partial_match_returns_matching_bbox():
    result = _run_locate("Search", [{"text": "Google Search", "x": 60, "y": 70, "width": 150, "height": 24, "conf": 88}])

    assert result["found"] is True
    assert result["bounding_boxes"][0]["x"] == 60
    assert result["bounding_boxes"][0]["y"] == 70
    assert result["bounding_boxes"][0]["width"] == 150
    assert result["bounding_boxes"][0]["height"] == 24


def test_locate_text_not_found_has_no_placeholder_bbox():
    result = _run_locate("Settings", [{"text": "Hello", "x": 5, "y": 6, "width": 50, "height": 15, "conf": 92}])

    assert result["found"] is False
    assert result["bounding_boxes"] == []
    assert "not found" in result["message"]


def test_locate_text_combines_nearby_words_on_the_same_line():
    result = _run_locate(
        "Sign In",
        [
            {"text": "Sign", "x": 100, "y": 120, "width": 40, "height": 20, "conf": 90},
            {"text": "In", "x": 150, "y": 120, "width": 20, "height": 20, "conf": 80},
            {"text": "Sign", "x": 10, "y": 220, "width": 40, "height": 20, "conf": 95, "line_num": 2},
        ],
    )

    assert result["found"] is True
    assert result["bounding_boxes"][0]["text"] == "Sign In"
    assert result["bounding_boxes"][0]["x"] == 100
    assert result["bounding_boxes"][0]["y"] == 120
    assert result["bounding_boxes"][0]["width"] == 70
    assert result["bounding_boxes"][0]["height"] == 20
    assert result["bounding_boxes"][0]["confidence"] == pytest.approx(0.85)


def test_ocr_screen_returns_word_boxes_and_ignores_invalid_confidence():
    tool = OcrScreenTool()
    image = Image.new("RGB", (400, 300), "white")
    words = [
        {"text": "Search", "x": 30, "y": 50, "width": 80, "height": 20, "conf": 97},
        {"text": "ignored", "x": 0, "y": 0, "width": 400, "height": 300, "conf": -1},
    ]
    with patch.object(tool, "_capture_desktop", return_value=image), patch("src.tools.vision.vision.pytesseract.image_to_data", return_value=_ocr_data(words)):
        result = tool.run()

    assert result["text"] == "Search"
    assert result["bounding_boxes"] == [{"text": "Search", "x": 30, "y": 50, "width": 80, "height": 20, "confidence": 0.97}]


def test_ocr_backend_failure_is_reported_as_tool_failure():
    tool = OcrScreenTool()
    image = Image.new("RGB", (400, 300), "white")

    with patch.object(tool, "_capture_desktop", return_value=image), patch(
        "src.tools.vision.vision.pytesseract.image_to_data",
        side_effect=RuntimeError("tesseract is not installed or it's not in PATH"),
    ):
        result = tool.run()

    assert result["success"] is False
    assert "OCR backend failed" in result["error"]


def test_screenshot_to_ocr_to_locate_text_flow():
    image = Image.new("RGB", (400, 300), "white")
    words = [{"text": "Search", "x": 200, "y": 150, "width": 75, "height": 22, "conf": 94}]
    ocr_tool = OcrScreenTool()
    locate_tool = LocateTextTool()

    with patch.object(ocr_tool, "_capture_desktop", return_value=image), patch.object(locate_tool, "_capture_desktop", return_value=image), patch("src.tools.vision.vision.pytesseract.image_to_data", return_value=_ocr_data(words)):
        ocr_result = ocr_tool.run()
        locate_result = locate_tool.run("Search")

    assert ocr_result["bounding_boxes"][0]["x"] == 200
    assert locate_result["found"] is True
    assert locate_result["bounding_boxes"][0]["x"] == 200
    assert locate_result["bounding_boxes"][0]["y"] == 150
    assert locate_result["bounding_boxes"][0]["width"] == 75
    assert locate_result["bounding_boxes"][0]["height"] == 22
