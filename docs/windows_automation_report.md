# Windows Automation Layer Report

## New files
- src/tools/windows/__init__.py
- src/tools/windows/launch_app.py
- src/tools/windows/windows.py
- src/tools/windows/mouse.py
- src/tools/windows/keyboard.py
- src/tools/windows/clipboard.py
- src/tools/windows/screenshot.py

## Modified files
- src/tools/registry.py

## Architecture
- Added a new package under src/tools/windows for generic desktop automation.
- Each tool inherits from the existing Tool base class.
- Tool discovery now walks nested packages so new automation modules are registered automatically.
- Tools return structured result dictionaries and log errors instead of printing.

## Example usage
### launch_app
```python
from src.tools.windows.launch_app import LaunchAppTool

tool = LaunchAppTool()
print(tool.run("notepad"))
```

### list_windows
```python
from src.tools.windows.windows import ListWindowsTool

tool = ListWindowsTool()
print(tool.run())
```

### find_window
```python
from src.tools.windows.windows import FindWindowTool

tool = FindWindowTool()
print(tool.run("Notepad"))
```

### focus_window
```python
from src.tools.windows.windows import FocusWindowTool

tool = FocusWindowTool()
print(tool.run("Notepad"))
```

### close_window
```python
from src.tools.windows.windows import CloseWindowTool

tool = CloseWindowTool()
print(tool.run("Notepad"))
```

### maximize_window
```python
from src.tools.windows.windows import MaximizeWindowTool

tool = MaximizeWindowTool()
print(tool.run("Notepad"))
```

### minimize_window
```python
from src.tools.windows.windows import MinimizeWindowTool

tool = MinimizeWindowTool()
print(tool.run("Notepad"))
```

### move_mouse
```python
from src.tools.windows.mouse import MoveMouseTool

tool = MoveMouseTool()
print(tool.run(100, 200))
```

### click
```python
from src.tools.windows.mouse import ClickTool

tool = ClickTool()
print(tool.run(100, 200))
```

### double_click
```python
from src.tools.windows.mouse import DoubleClickTool

tool = DoubleClickTool()
print(tool.run(100, 200))
```

### right_click
```python
from src.tools.windows.mouse import RightClickTool

tool = RightClickTool()
print(tool.run(100, 200))
```

### drag
```python
from src.tools.windows.mouse import DragTool

tool = DragTool()
print(tool.run(100, 100, 300, 300))
```

### press_key
```python
from src.tools.windows.keyboard import PressKeyTool

tool = PressKeyTool()
print(tool.run("enter"))
```

### hotkey
```python
from src.tools.windows.keyboard import HotkeyTool

tool = HotkeyTool()
print(tool.run(keys=["ctrl", "c"]))
```

### type_text
```python
from src.tools.windows.keyboard import TypeTextTool

tool = TypeTextTool()
print(tool.run("hello"))
```

### copy
```python
from src.tools.windows.clipboard import CopyTool

tool = CopyTool()
print(tool.run("hello from clipboard"))
```

### paste
```python
from src.tools.windows.clipboard import PasteTool

tool = PasteTool()
print(tool.run())
```

### take_screenshot
```python
from src.tools.windows.screenshot import TakeScreenshotTool

tool = TakeScreenshotTool()
print(tool.run())
```

### capture_window
```python
from src.tools.windows.screenshot import CaptureWindowTool

tool = CaptureWindowTool()
print(tool.run("Notepad"))
```

## Verification
- Registry discovery confirmed 21 tool names, including the new Windows automation tools.
- Main application startup completed successfully.
