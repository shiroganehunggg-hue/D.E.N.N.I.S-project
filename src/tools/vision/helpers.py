import logging
from typing import Any, Dict

logger = logging.getLogger(__name__)


def build_result(text: str = "", bounding_boxes: list | None = None, icons: list | None = None, buttons: list | None = None) -> Dict[str, Any]:
    """Return a structured result object for vision operations."""
    return {
        "text": text or "",
        "bounding_boxes": bounding_boxes or [],
        "icons": icons or [],
        "buttons": buttons or [],
    }
