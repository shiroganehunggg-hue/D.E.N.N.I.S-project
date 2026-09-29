# Vision subsystem

## Overview
The Vision subsystem gives DENNIS a lightweight way to inspect the current screen before interacting with desktop applications.

## Available tools
- take_desktop_screenshot
- ocr_screen
- get_active_window_screenshot
- locate_text

## Example usage
```python
from src.tools.vision.vision import TakeDesktopScreenshotTool

tool = TakeDesktopScreenshotTool()
print(tool.run())
```

```python
from src.tools.vision.vision import OcrScreenTool

tool = OcrScreenTool()
print(tool.run())
```

```python
from src.tools.vision.vision import LocateTextTool

tool = LocateTextTool()
print(tool.run("Save"))
```

## Notes
- `ocr_screen` and `locate_text` use Tesseract to return recognized text and coordinates.
- Screenshot tools save images locally; they do not send images to a vision model.
- Icon, button, and text-region detection are not exposed until a real detector is implemented.
