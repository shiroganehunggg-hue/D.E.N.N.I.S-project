import json
import unittest
from unittest.mock import patch

from src.core.dennis import Dennis
from src.core.planner.models import ErrorDecision, ExecutionResult, Plan, PlanStep, ToolResult
from src.core.planner.reflection import PlanReflector
from src.providers.provider_result import ProviderResult
from src.tools.manager import ToolManager


class FakeMemory:
    def __init__(self):
        self.facts = []
        self.messages = []

    def add_message(self, role, content):
        self.messages.append({"role": role, "content": content})

    def add_fact(self, text):
        self.facts.append({"text": text})

    def add_or_replace_fact(self, fact, replace_fact=None):
        self.facts.append({"text": fact})

    def remove_fact_matching(self, user_prompt):
        return None

    def clear_facts(self):
        self.facts = []


class FakeBuilder:
    def build(self, memory, user_prompt):
        return [{"role": "user", "content": user_prompt}]


class FakeClassifier:
    def classify(self, user_input, existing_facts=None):
        return {"intent": "chat", "fact": None, "replace_fact": None}


class RecordingToolManager:
    def __init__(self):
        self.calls = []

    def get_schemas(self):
        return []

    def to_openai_tool_format(self):
        return []

    def call(self, name, **kwargs):
        self.calls.append((name, kwargs))
        return ToolResult(tool=name, success=True, result=f"ok:{name}:{kwargs}")


class FailingToolManager(RecordingToolManager):
    def call(self, name, **kwargs):
        self.calls.append((name, kwargs))
        return ToolResult(tool=name, success=False, error="application not found")


class EmptyResultTool:
    name = "empty_result"
    description = "test tool"

    def run(self):
        return ""

    def schema(self):
        return {"name": self.name, "description": self.description, "parameters": {"type": "object", "properties": {}, "required": []}}


class FakeRouter:
    def __init__(self):
        self.calls = []

    def generate(self, messages, tools=None, tool_system_message=None):
        self.calls.append({
            "messages": list(messages),
            "tools": tools,
            "tool_system_message": tool_system_message,
        })
        if len(self.calls) == 1:
            return ProviderResult(
                success=True,
                content="",
                tool_calls=[{
                    "id": "call_1",
                    "function": {
                        "name": "lookup_weather",
                        "arguments": '{"city": "Hanoi"}',
                    },
                }],
                provider="fake",
            )
        return ProviderResult(
            success=True,
            content="Final answer from second call",
            provider="fake",
        )


class HallucinatingAfterFailureRouter(FakeRouter):
    def generate(self, messages, tools=None, tool_system_message=None):
        self.calls.append({
            "messages": list(messages),
            "tools": tools,
            "tool_system_message": tool_system_message,
        })
        if len(self.calls) == 1:
            return ProviderResult(
                success=True,
                content="",
                tool_calls=[{
                    "id": "call_1",
                    "function": {"name": "open_app", "arguments": '{"app_name": "spotify"}'},
                }],
                provider="fake",
            )
        return ProviderResult(success=True, content="I've opened Spotify.", provider="fake")


class PromptFallbackFailureRouter(FakeRouter):
    def generate(self, messages, tools=None, tool_system_message=None):
        self.calls.append({"messages": list(messages), "tools": tools, "tool_system_message": tool_system_message})
        if len(self.calls) == 1:
            return ProviderResult(
                success=True,
                content='TOOL_CALL: {"name": "browser", "args": {"action": "open_url", "url": "https://open.spotify.com"}}',
                provider="fake",
            )
        return ProviderResult(success=True, content="I've opened Spotify's web interface.", provider="fake")


class NoKeyProvider:
    def __init__(self, client=None, result=None):
        self.client = client
        self.supports_tool_calling_native = True
        self.result = result or ProviderResult(success=True, content="ok:NoKeyProvider", provider="NoKeyProvider")
        self.called = False

    def generate(self, messages, tools=None):
        self.called = True
        return self.result


class GoodProvider:
    def __init__(self, client=None, result=None):
        self.client = client
        self.supports_tool_calling_native = True
        self.result = result or ProviderResult(success=True, content="ok:GoodProvider", provider="GoodProvider")
        self.called = False

    def generate(self, messages, tools=None):
        self.called = True
        return self.result


class DennisToolCallParsingTests(unittest.TestCase):
    def test_manager_does_not_turn_an_empty_tool_result_into_success(self):
        manager = ToolManager()
        manager.register(EmptyResultTool())

        result = manager.call("empty_result")

        self.assertFalse(result.success)
        self.assertIn("empty result", result.error)

    def test_extract_tool_calls_parses_multiple_blocks(self):
        dennis = Dennis.__new__(Dennis)
        answer = (
            "Need two actions.\n"
            'TOOL_CALL: {"name": "open_app", "args": {"name": "notepad"}}\n'
            'TOOL_CALL: {"name": "type_text", "args": {"text": "hello"}}\n'
        )

        tool_calls = dennis._extract_tool_calls(answer)

        self.assertEqual(len(tool_calls), 2)
        self.assertEqual(tool_calls[0]["name"], "open_app")
        self.assertEqual(tool_calls[1]["name"], "type_text")

    def test_extract_tool_calls_returns_empty_when_absent(self):
        dennis = Dennis.__new__(Dennis)
        answer = "No tool call here, just a normal reply."

        tool_calls = dennis._extract_tool_calls(answer)

        self.assertEqual(tool_calls, [])

    def test_ask_executes_native_tool_calls_and_uses_second_response_content(self):
        dennis = Dennis.__new__(Dennis)
        dennis.memory = FakeMemory()
        dennis.builder = FakeBuilder()
        dennis.classifier = FakeClassifier()
        dennis.tool_manager = RecordingToolManager()
        dennis.router = FakeRouter()
        dennis._build_tool_system_message = lambda: {"role": "system", "content": "tool system"}
        dennis._should_use_planner = lambda prompt, intent=None: False

        answer = dennis.ask("Hanoi weather")

        self.assertEqual(answer, "Final answer from second call")
        self.assertEqual(dennis.tool_manager.calls, [("lookup_weather", {"city": "Hanoi"})])
        self.assertEqual(len(dennis.router.calls), 2)
        second_messages = dennis.router.calls[1]["messages"]
        self.assertTrue(any(msg.get("role") == "tool" and msg.get("tool_call_id") == "call_1" for msg in second_messages))

    def test_native_tool_failure_is_explicit_and_cannot_be_reported_as_success(self):
        dennis = Dennis.__new__(Dennis)
        dennis.memory = FakeMemory()
        dennis.builder = FakeBuilder()
        dennis.classifier = FakeClassifier()
        dennis.tool_manager = FailingToolManager()
        dennis.router = HallucinatingAfterFailureRouter()
        dennis._build_tool_system_message = lambda: {"role": "system", "content": "tool system"}
        dennis._should_use_planner = lambda prompt, intent=None: False

        answer = dennis.ask("Open Spotify")

        self.assertIn("open_app", answer)
        self.assertIn("application not found", answer)
        self.assertNotIn("I've opened Spotify", answer)
        tool_message = next(message for message in dennis.router.calls[1]["messages"] if message.get("role") == "tool")
        payload = json.loads(tool_message["content"])
        self.assertEqual(payload["success"], False)
        self.assertEqual(payload["error"], "application not found")

    def test_prompt_tool_loop_blocks_an_unrelated_fallback_after_failure(self):
        dennis = Dennis.__new__(Dennis)
        dennis.tool_manager = FailingToolManager()
        dennis.router = PromptFallbackFailureRouter()

        answer = dennis._run_tool_loop(
            [{"role": "user", "content": "Open Spotify and locate visible text"}],
            'TOOL_CALL: {"name": "open_app", "args": {"app_name": "spotify"}}',
            [{"name": "open_app", "args": {"app_name": "spotify"}}],
        )

        self.assertIn("open_app", answer)
        self.assertIn("application not found", answer)
        self.assertNotIn("I've opened Spotify's web interface", answer)
        self.assertEqual(dennis.tool_manager.calls, [("open_app", {"app_name": "spotify"})])

    def test_tool_loop_passes_tool_schemas_back_to_router_after_tool_results(self):
        dennis = Dennis.__new__(Dennis)
        dennis.tool_manager = RecordingToolManager()
        dennis.router = FakeRouter()
        dennis._build_tool_system_message = lambda: {"role": "system", "content": "tool system"}

        dennis._run_tool_loop(
            [{"role": "user", "content": "Check screen"}],
            'TOOL_CALL: {"name": "lookup_weather", "args": {"city": "Hanoi"}}',
            [{"name": "lookup_weather", "args": {"city": "Hanoi"}}],
        )

        self.assertIsNotNone(dennis.router.calls[1]["tools"])
        self.assertEqual(dennis.router.calls[1]["tool_system_message"], {"role": "system", "content": "tool system"})

    def test_router_skips_providers_without_configured_clients(self):
        no_key_provider = NoKeyProvider(client=None)
        good_provider = GoodProvider(client=object())

        router = __import__("src.core.provider_router", fromlist=["ProviderRouter"]).ProviderRouter(
            [no_key_provider, good_provider],
            metrics=__import__("src.core.metrics", fromlist=["ProviderMetrics"]).ProviderMetrics(storage_path=None),
        )

        result = router.generate([{"role": "user", "content": "hello"}])

        self.assertTrue(good_provider.called)
        self.assertFalse(no_key_provider.called)
        self.assertTrue(result.success)
        self.assertEqual(result.provider, "GoodProvider")

    def test_dennis_initializes_when_no_provider_is_configured(self):
        with patch("src.core.dennis.ProviderFactory.create_all", return_value=[]):
            dennis = Dennis()

        self.assertEqual(dennis.providers, [])
        self.assertIsNone(dennis.gemini)
        self.assertIsNone(dennis.groq)
        self.assertIsNone(dennis.memory.summarizer)

    def test_action_request_skips_the_pre_planner_chat_completion(self):
        class ActionClassifier:
            def classify(self, user_input, existing_facts=None):
                return {"intent": "action", "fact": None, "replace_fact": None}

        class StubPlanner:
            def create_plan(self, user_request, memory_summary="", context=""):
                return Plan(goal=user_request, steps=[PlanStep(tool="test_action")])

        class StubExecutor:
            def execute(self, plan):
                return ExecutionResult(goal=plan.goal, completed=True)

        dennis = Dennis.__new__(Dennis)
        dennis.memory = FakeMemory()
        dennis.builder = FakeBuilder()
        dennis.classifier = ActionClassifier()
        dennis.tool_manager = RecordingToolManager()
        dennis.router = FakeRouter()
        dennis.planner = StubPlanner()
        dennis.executor = StubExecutor()
        dennis.reflector = PlanReflector()
        dennis._build_tool_system_message = lambda: {"role": "system", "content": "tools"}

        answer = dennis.ask("Open Spotify")

        self.assertIn("hoàn thành", answer)
        self.assertEqual(dennis.router.calls, [])

    def test_ask_skips_planner_for_chat_intent_and_returns_llm_reply(self):
        dennis = Dennis.__new__(Dennis)
        dennis.memory = FakeMemory()
        dennis.builder = FakeBuilder()
        class CountingClassifier:
            def __init__(self):
                self.calls = 0

            def classify(self, user_input, existing_facts=None):
                self.calls += 1
                return {"intent": "chat", "fact": None, "replace_fact": None}

        classifier = CountingClassifier()
        dennis.classifier = classifier
        dennis.tool_manager = RecordingToolManager()
        dennis.router = type("R", (), {"generate": lambda self, messages, tools=None, tool_system_message=None: type("Res", (), {"content": "Tôi đang trò chuyện bình thường.", "tool_calls": None})()})()
        dennis._build_tool_system_message = lambda: {"role": "system", "content": "tool system"}

        self.assertFalse(dennis._should_use_planner("haha còn xa mới đi làm", intent="chat"))
        self.assertEqual(dennis.ask("haha còn xa mới đi làm"), "Tôi đang trò chuyện bình thường.")
        self.assertEqual(classifier.calls, 1)

    def test_reflector_produces_clear_actionable_summary_for_replan(self):
        execution = ExecutionResult(
            goal="Open Spotify",
            completed=False,
            error_decision=ErrorDecision.REPLAN,
            failure_reason="ứng dụng hoặc đường dẫn sai",
            failed_step=PlanStep(tool="launch_app", args={"app_name_or_path": "spotify"}),
        )

        summary = PlanReflector().reflect("Open Spotify", execution).summary

        self.assertIn("đổi cách", summary.lower())
        self.assertIn("launch_app", summary.lower())
        self.assertIn("ứng dụng", summary.lower())


if __name__ == "__main__":
    unittest.main()
