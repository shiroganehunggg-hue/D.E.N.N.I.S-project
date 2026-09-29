import subprocess
import unittest
from unittest.mock import patch

from src.core.planner.models import Plan, PlanStep
from src.core.planner.planner import Planner
from src.core.planner.executor import PlanExecutor
from src.providers.provider_result import ProviderResult
from src.tools.manager import ToolManager


class FakeRouter:
    def generate(self, messages):
        return ProviderResult(
            success=True,
            content='{"goal":"Open Notepad","steps":[{"tool":"launch_app","args":{"app_name_or_path":"notepad"},"retries":1},{"tool":"focus_window","args":{"title":"Notepad"},"retries":1}]}',
        )


class DesktopAgentPipelineTests(unittest.TestCase):
    def test_planner_returns_json_only_plan(self):
        tool_manager = ToolManager()
        from src.tools.windows.launch_app import LaunchAppTool
        from src.tools.windows.windows import FocusWindowTool
        tool_manager.register(LaunchAppTool())
        tool_manager.register(FocusWindowTool())

        planner = Planner(tool_manager, FakeRouter())
        plan = planner.create_plan("Open Notepad")

        self.assertEqual(plan.goal, "Open Notepad")
        self.assertEqual(len(plan.steps), 2)
        self.assertEqual(plan.steps[0].tool, "launch_app")
        self.assertEqual(plan.steps[1].tool, "focus_window")

    def test_executor_stops_on_failed_step(self):
        tool_manager = ToolManager()
        from src.tools.windows.launch_app import LaunchAppTool
        tool_manager.register(LaunchAppTool())

        executor = PlanExecutor(tool_manager)
        plan = Plan(goal="Open missing app", steps=[PlanStep(tool="launch_app", args={"app_name_or_path": "__missing__"}, retries=0)])
        result = executor.execute(plan)

        self.assertFalse(result.completed)
        self.assertEqual(len(result.tool_results), 1)
        self.assertFalse(result.tool_results[0].success)

    def test_fallback_plan_uses_process_name_for_focus(self):
        tool_manager = ToolManager()
        planner = Planner(tool_manager, None)

        plan = planner._fallback_plan("Open Notepad")

        self.assertEqual(plan.steps[0].tool, "launch_app")
        self.assertEqual(plan.steps[1].tool, "focus_window")
        self.assertEqual(plan.steps[1].args.get("process_name"), "notepad.exe")

    def test_fallback_plan_routes_spotify_intents_and_extracts_track_query(self):
        tool_manager = ToolManager()
        planner = Planner(tool_manager, None)

        play_plan = planner._fallback_plan("Play Nơi này có anh by Sơn Tùng on Spotify")
        open_plan = planner._fallback_plan("Open Spotify")
        search_plan = planner._fallback_plan("Search for Nơi này có anh on Spotify")

        self.assertEqual(play_plan.steps[0].tool, "spotify")
        self.assertEqual(play_plan.steps[0].args, {"action": "play", "query": "Nơi này có anh by Sơn Tùng"})
        self.assertEqual(open_plan.steps[0].args, {"action": "open"})
        self.assertEqual(search_plan.steps[0].args, {"action": "search", "query": "Nơi này có anh"})

    def test_executor_reuses_hwnd_from_launch_for_focus(self):
        class StubLaunchTool:
            name = "launch_app"
            description = "stub"

            def run(self, app_name_or_path: str):
                return {
                    "success": True,
                    "result": "launched",
                    "data": {"pid": 1234, "hwnd": 5678, "process_name": "notepad.exe", "executable_name": "notepad.exe", "title": "Untitled - Notepad"},
                }

            def schema(self):
                return {"name": self.name, "description": self.description, "parameters": {"type": "object", "properties": {"app_name_or_path": {"type": "string"}}, "required": ["app_name_or_path"]}}

        class StubFocusTool:
            name = "focus_window"
            description = "stub"

            def run(self, **kwargs):
                return {"success": True, "result": "focused", "data": kwargs}

            def schema(self):
                return {"name": self.name, "description": self.description, "parameters": {"type": "object", "properties": {"hwnd": {"type": "integer"}}, "required": []}}

        tool_manager = ToolManager()
        tool_manager.register(StubLaunchTool())
        tool_manager.register(StubFocusTool())

        executor = PlanExecutor(tool_manager)
        plan = Plan(goal="Open Notepad", steps=[PlanStep(tool="launch_app", args={"app_name_or_path": "notepad"}, retries=0), PlanStep(tool="focus_window", args={}, retries=0)])
        result = executor.execute(plan)

        self.assertTrue(result.completed)
        self.assertEqual(result.tool_results[1].data.get("hwnd"), 5678)

    def test_executor_reuses_launch_state_for_duplicate_launch_steps(self):
        class StubLaunchTool:
            name = "launch_app"
            description = "stub"

            def run(self, app_name_or_path: str):
                return {
                    "success": True,
                    "result": f"launched {app_name_or_path}",
                    "data": {"target": app_name_or_path, "pid": 1234, "hwnd": 5678, "process_name": "calculator.exe"},
                }

            def schema(self):
                return {"name": self.name, "description": self.description, "parameters": {"type": "object", "properties": {"app_name_or_path": {"type": "string"}}, "required": ["app_name_or_path"]}}

        tool_manager = ToolManager()
        tool_manager.register(StubLaunchTool())

        executor = PlanExecutor(tool_manager)
        plan = Plan(
            goal="Open Calculator and type 25+36=",
            steps=[
                PlanStep(tool="launch_app", args={"app_name_or_path": "calculator"}, retries=0),
                PlanStep(tool="launch_app", args={"app_name_or_path": "calculator"}, retries=0),
            ],
        )
        result = executor.execute(plan)

        self.assertTrue(result.completed)
        self.assertEqual(len(result.tool_results), 2)
        self.assertTrue(result.tool_results[0].success)
        self.assertTrue(result.tool_results[1].success)
        self.assertEqual(result.tool_results[1].data.get("reused"), True)

    def test_open_app_reports_failure_when_process_never_starts(self):
        from src.tools.open_app import OpenAppTool

        with patch("src.tools.open_app.os.startfile") as startfile_mock, patch(
            "src.tools.open_app.subprocess.run",
            return_value=subprocess.CompletedProcess(args=["tasklist"], returncode=0, stdout="", stderr=""),
        ):
            result = OpenAppTool().run("spotify")

        self.assertFalse(result["success"])
        self.assertIn("không mở được", str(result.get("error", "")).lower())


if __name__ == "__main__":
    unittest.main()
