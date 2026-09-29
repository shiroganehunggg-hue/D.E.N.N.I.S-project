from __future__ import annotations

import logging
import time
from typing import List, Optional

from src.core.planner.error_handler import ErrorAnalyzer
from src.core.planner.models import ErrorDecision, ExecutionResult, Plan, ToolResult
from src.tools.manager import ToolManager

DEFAULT_WINDOW_TIMEOUT = 10.0
DEFAULT_ACTION_DELAY = 0.3
DEFAULT_FOCUS_DELAY = 0.5
DEFAULT_RETRY_DELAY = 0.3

logger = logging.getLogger(__name__)


class PlanExecutor:
    """Execute a plan sequentially without calling the LLM again to re-plan.

    On step failure, an ErrorAnalyzer (LLM-based) decides retry / skip /
    replan / abort instead of blindly retrying step.retries times. "replan"
    and "abort" both stop execution here and bubble up via
    ExecutionResult.error_decision — the caller (Dennis) decides what to do
    next (a future replan loop reacts to REPLAN specifically).
    """

    def __init__(self, tool_manager: ToolManager, error_analyzer: Optional[ErrorAnalyzer] = None):
        self.tool_manager = tool_manager
        self.error_analyzer = error_analyzer

    def execute(self, plan: Plan) -> ExecutionResult:
        tool_results: List[ToolResult] = []
        launch_state: dict = {}

        logger.info("[PLAN] %s", plan.goal)
        for index, step in enumerate(plan.steps, 1):
            logger.info("[STEP %s] %s", index, step.tool or "<empty>")

            if not step.tool:
                failure = ToolResult(tool="", success=False, result="", error="Empty tool name")
                tool_results.append(failure)
                logger.error("[STEP %s] FAILED: %s", index, failure.error)
                return ExecutionResult(
                    goal=plan.goal, completed=False, tool_results=tool_results,
                    failure_reason=failure.error, failed_step=step,
                )

            max_attempts = step.retries + 1
            attempt = 0

            while True:
                attempt += 1
                start = time.time()
                exc_text: Optional[str] = None

                try:
                    if step.tool == "launch_app" and self._is_reused_launch(step.args.get("app_name_or_path"), launch_state):
                        logger.info("[STEP %s] Launch reused for %s", index, step.args.get("app_name_or_path"))
                        result = ToolResult(tool=step.tool, success=True, result="Launch reused", data={"reused": True, **launch_state})
                    else:
                        if step.tool == "launch_app" and launch_state.get("app_name"):
                            logger.info("[STEP %s] Launch retry for %s", index, step.args.get("app_name_or_path"))
                        step_args = dict(step.args or {})
                        if step.tool == "focus_window":
                            if step_args.get("hwnd") is None and launch_state.get("hwnd") is not None:
                                step_args["hwnd"] = launch_state["hwnd"]
                            if not step_args.get("process_name") and launch_state.get("process_name"):
                                step_args["process_name"] = launch_state["process_name"]
                            if not step_args.get("executable_name") and launch_state.get("executable_name"):
                                step_args["executable_name"] = launch_state["executable_name"]
                            if not step_args.get("title") and launch_state.get("title"):
                                step_args["title"] = launch_state["title"]
                        result = self.tool_manager.call(step.tool, **step_args)
                        if step.tool == "launch_app" and getattr(result, "success", False):
                            data = result.data if isinstance(result.data, dict) else {}
                            launch_state = {
                                "app_name": step.args.get("app_name_or_path"),
                                "pid": data.get("pid"),
                                "hwnd": data.get("hwnd"),
                                "process_name": data.get("process_name") or data.get("process"),
                                "title": data.get("title"),
                                "executable_name": data.get("executable_name"),
                            }
                except Exception as exc:
                    exc_text = str(exc)
                    result = ToolResult(tool=step.tool, success=False, result="", error=exc_text)

                duration_ms = int((time.time() - start) * 1000)
                if result.duration_ms is None:
                    result.duration_ms = duration_ms
                if result.duration_seconds is None:
                    result.duration_seconds = duration_ms / 1000.0

                if result.success:
                    tool_results.append(result)
                    logger.info("[STEP %s] %s SUCCESS %s ms", index, step.tool, result.duration_ms)
                    break

                # Step thất bại (raise exception hoặc trả success=False) —
                # hỏi ErrorAnalyzer thay vì retry mù như trước.
                error_text = result.error or exc_text or "Unknown error"
                logger.warning("[STEP %s] %s attempt %s/%s FAILED: %s", index, step.tool, attempt, max_attempts, error_text)

                if self.error_analyzer is None:
                    # Không có analyzer (vd chưa cấu hình router) -> giữ
                    # hành vi cũ: retry tới hết step.retries rồi bỏ cuộc.
                    if attempt >= max_attempts:
                        tool_results.append(result)
                        logger.error("[STEP %s] %s FAILED sau %s lần: %s", index, step.tool, attempt, error_text)
                        return ExecutionResult(
                            goal=plan.goal, completed=False, tool_results=tool_results,
                            failure_reason=error_text, failed_step=step,
                        )
                    time.sleep(DEFAULT_RETRY_DELAY)
                    continue

                analysis = self.error_analyzer.analyze(step, error_text, attempt, max_attempts)

                if analysis.decision == ErrorDecision.RETRY and attempt < max_attempts:
                    logger.info("[STEP %s] Retry theo quyết định của analyzer: %s", index, analysis.reason)
                    time.sleep(DEFAULT_RETRY_DELAY)
                    continue

                if analysis.decision == ErrorDecision.SKIP:
                    skip_result = ToolResult(
                        tool=step.tool, success=True,
                        result=f"Đã bỏ qua bước này: {analysis.reason or 'không quan trọng'}",
                        data={"skipped": True, "original_error": error_text},
                    )
                    tool_results.append(skip_result)
                    logger.info("[STEP %s] SKIPPED (%s)", index, analysis.reason)
                    break

                # REPLAN, ABORT, hoặc RETRY nhưng đã hết lượt thử -> dừng
                # thực thi plan, trả kết quả kèm quyết định để tầng trên
                # (Dennis / vòng lặp replan sau này) xử lý tiếp.
                tool_results.append(result)
                logger.error(
                    "[STEP %s] %s FAILED -> quyết định %s: %s",
                    index, step.tool, analysis.decision.value, analysis.reason or error_text,
                )
                return ExecutionResult(
                    goal=plan.goal, completed=False, tool_results=tool_results,
                    failure_reason=analysis.reason or error_text,
                    error_decision=analysis.decision,
                    failed_step=step,
                )

            if step.tool == "launch_app":
                self._wait_for_window(timeout=DEFAULT_WINDOW_TIMEOUT)
                time.sleep(DEFAULT_ACTION_DELAY)
            elif step.tool == "focus_window":
                time.sleep(DEFAULT_FOCUS_DELAY)
            elif step.tool in {"type_text", "press_key", "hotkey", "click", "double_click", "right_click"}:
                time.sleep(DEFAULT_ACTION_DELAY)

        return ExecutionResult(goal=plan.goal, completed=True, tool_results=tool_results)

    def _wait_for_window(self, timeout: float = DEFAULT_WINDOW_TIMEOUT) -> bool:
        deadline = time.time() + timeout
        while time.time() < deadline:
            window_result = self.tool_manager.call("list_windows")
            if window_result.success and window_result.data:
                return True
            time.sleep(0.1)
        return False

    def _is_reused_launch(self, app_name: str | None, launch_state: dict) -> bool:
        if not app_name:
            return False
        return bool(launch_state.get("app_name") and str(launch_state.get("app_name")).lower() == str(app_name).lower())
