# Planner examples

## Example 1: open an app
```json
{
  "goal": "Open Notepad",
  "steps": [
    {"tool": "launch_app", "args": {"app_name_or_path": "notepad"}, "retries": 1}
  ]
}
```

## Example 2: create a file
```json
{
  "goal": "Create a Python file in VS Code",
  "steps": [
    {"tool": "launch_app", "args": {"app_name_or_path": "Code"}, "retries": 1},
    {"tool": "focus_window", "args": {"title": "Visual Studio Code"}, "retries": 1},
    {"tool": "type_text", "args": {"text": "print('Hello World')"}, "retries": 1}
  ]
}
```

## Example 3: inspect and act
```json
{
  "goal": "Inspect the screen and open the browser",
  "steps": [
    {"tool": "take_desktop_screenshot", "args": {}, "retries": 1},
    {"tool": "launch_app", "args": {"app_name_or_path": "chrome"}, "retries": 1}
  ]
}
```
