import unittest

from src.core.planner.error_handler import ErrorAnalyzer
from src.core.planner.executor import PlanExecutor
from src.core.planner.models import ErrorDecision, Plan, PlanStep
from src.providers.provider_result import ProviderResult


class ScriptedRouter:
    """Trả lần lượt các quyết định đã định sẵn cho mỗi lần analyze() gọi."""

    def __init__(self, responses):
        self._responses = list(responses)
        self.calls = 0

    def generate(self, messages):
        self.calls += 1
        if not self._responses:
            content = '{"decision":"abort","reason":"no more scripted responses","user_message":""}'
        else:
            content = self._responses.pop(0)
        return ProviderResult(success=True, content=content)


class FailNTimesTool:
    name = "flaky_tool"
    description = "fails a fixed number of times then succeeds"

    def __init__(self, fail_times: int):
        self.fail_times = fail_times
        self.calls = 0

    def run(self, **kwargs):
        self.calls += 1
        if self.calls <= self.fail_times:
            return {"success": False, "error": f"boom attempt {self.calls}"}
        return {"success": True, "result": "ok"}

    def schema(self):
        return {"name": self.name, "description": self.description, "parameters": {"type": "object", "properties": {}, "required": []}}


class AlwaysFailTool:
    name = "flaky_tool"
    description = "always fails"

    def run(self, **kwargs):
        return {"success": False, "error": "always boom"}

    def schema(self):
        return {"name": self.name, "description": self.description, "parameters": {"type": "object", "properties": {}, "required": []}}


class ErrorAnalyzerTests(unittest.TestCase):
    def test_analyze_parses_retry_decision(self):
        router = ScriptedRouter(['{"decision":"retry","reason":"timeout tạm thời","user_message":"Thử lại nhé sếp."}'])
        analyzer = ErrorAnalyzer(router)
        step = PlanStep(tool="flaky_tool", args={}, retries=2)

        analysis = analyzer.analyze(step, "network timeout", attempt=1, max_attempts=3)

        self.assertEqual(analysis.decision, ErrorDecision.RETRY)
        self.assertIn("timeout", analysis.reason)

    def test_analyze_still_asks_llm_on_last_attempt_so_skip_abort_remain_possible(self):
        router = ScriptedRouter(['{"decision":"skip","reason":"không quan trọng","user_message":""}'])
        analyzer = ErrorAnalyzer(router)
        step = PlanStep(tool="flaky_tool", args={}, retries=0)

        analysis = analyzer.analyze(step, "boom", attempt=1, max_attempts=1)

        self.assertEqual(analysis.decision, ErrorDecision.SKIP)
        self.assertEqual(router.calls, 1)

    def test_analyze_upgrades_skip_to_replan_for_critical_step(self):
        router = ScriptedRouter(['{"decision":"skip","reason":"not important","user_message":""}'])
        analyzer = ErrorAnalyzer(router)
        step = PlanStep(tool="flaky_tool", args={}, retries=1, critical=True)

        analysis = analyzer.analyze(step, "boom", attempt=1, max_attempts=2)

        self.assertEqual(analysis.decision, ErrorDecision.REPLAN)

    def test_analyze_uses_heuristics_for_missing_app_or_bad_path(self):
        router = ScriptedRouter(['{"decision":"retry","reason":"có thể do timeout","user_message":""}'])
        analyzer = ErrorAnalyzer(router)
        step = PlanStep(tool="launch_app", args={"app_name_or_path": "__missing__"}, retries=1)

        analysis = analyzer.analyze(step, "[WinError 2] The system cannot find the file specified: '__missing__'", attempt=1, max_attempts=2)

        self.assertEqual(analysis.decision, ErrorDecision.REPLAN)

    def test_analyze_falls_back_to_replan_on_malformed_llm_output(self):
        router = ScriptedRouter(["not valid json at all"])
        analyzer = ErrorAnalyzer(router)
        step = PlanStep(tool="flaky_tool", args={}, retries=1)

        analysis = analyzer.analyze(step, "boom", attempt=1, max_attempts=2)

        self.assertEqual(analysis.decision, ErrorDecision.REPLAN)


class PlanExecutorErrorAnalyzerIntegrationTests(unittest.TestCase):
    def test_executor_retries_result_based_failure_using_analyzer_decision(self):
        from src.tools.manager import ToolManager

        tool = FailNTimesTool(fail_times=1)
        tool_manager = ToolManager()
        tool_manager.register(tool)

        router = ScriptedRouter(['{"decision":"retry","reason":"tạm thời","user_message":""}'])
        analyzer = ErrorAnalyzer(router)
        executor = PlanExecutor(tool_manager, analyzer)

        plan = Plan(goal="test", steps=[PlanStep(tool="flaky_tool", args={}, retries=1)])
        result = executor.execute(plan)

        self.assertTrue(result.completed)
        self.assertEqual(tool.calls, 2)

    def test_executor_skips_step_when_analyzer_says_skip(self):
        from src.tools.manager import ToolManager

        tool_manager = ToolManager()
        tool_manager.register(AlwaysFailTool())

        router = ScriptedRouter(['{"decision":"skip","reason":"không quan trọng","user_message":""}'])
        analyzer = ErrorAnalyzer(router)
        executor = PlanExecutor(tool_manager, analyzer)

        plan = Plan(goal="test", steps=[PlanStep(tool="flaky_tool", args={}, retries=0)])
        result = executor.execute(plan)

        self.assertTrue(result.completed)
        self.assertTrue(result.tool_results[0].data.get("skipped"))

    def test_executor_stops_and_reports_replan_decision(self):
        from src.tools.manager import ToolManager

        tool_manager = ToolManager()
        tool_manager.register(AlwaysFailTool())

        router = ScriptedRouter(['{"decision":"replan","reason":"sai cách tiếp cận","user_message":""}'])
        analyzer = ErrorAnalyzer(router)
        executor = PlanExecutor(tool_manager, analyzer)

        plan = Plan(goal="test", steps=[PlanStep(tool="flaky_tool", args={}, retries=0)])
        result = executor.execute(plan)

        self.assertFalse(result.completed)
        self.assertEqual(result.error_decision, ErrorDecision.REPLAN)
        self.assertEqual(result.failed_step.tool, "flaky_tool")

    def test_executor_without_analyzer_keeps_old_blind_retry_behavior(self):
        from src.tools.manager import ToolManager

        tool_manager = ToolManager()
        tool_manager.register(AlwaysFailTool())

        executor = PlanExecutor(tool_manager)  # không truyền analyzer
        plan = Plan(goal="test", steps=[PlanStep(tool="flaky_tool", args={}, retries=0)])
        result = executor.execute(plan)

        self.assertFalse(result.completed)
        self.assertIsNone(result.error_decision)


if __name__ == "__main__":
    unittest.main()
