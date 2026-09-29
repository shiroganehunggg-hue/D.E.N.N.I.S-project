from src.core.planner.models import ToolResult
from src.tools.manager import ToolManager


class ConfirmableTool:
    name = "write_file"
    description = "test tool"

    def __init__(self):
        self.called = False

    def run(self, value):
        self.called = True
        return {"success": True, "result": value}

    def schema(self):
        return {"name": self.name, "description": self.description, "parameters": {"type": "object", "properties": {}, "required": []}}


def test_confirmation_required_tool_is_denied_by_default():
    manager = ToolManager()
    tool = ConfirmableTool()
    manager.register(tool)

    result = manager.call("write_file", value="content")

    assert isinstance(result, ToolResult)
    assert result.success is False
    assert "requires user confirmation" in result.error
    assert tool.called is False


def test_confirmation_callback_controls_execution():
    manager = ToolManager()
    tool = ConfirmableTool()
    manager.register(tool)
    manager.set_approval_callback(lambda name, arguments: name == "write_file" and arguments["value"] == "content")

    result = manager.call("write_file", value="content")

    assert result.success is True
    assert tool.called is True