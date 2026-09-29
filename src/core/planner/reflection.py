from __future__ import annotations

from src.core.planner.models import ErrorDecision, ExecutionResult, ReflectionResult

_DECISION_PHRASING = {
    ErrorDecision.REPLAN: "cần đổi cách thực hiện để tiếp tục",
    ErrorDecision.ABORT: "không thể tiếp tục vì điều kiện không cho phép",
    ErrorDecision.RETRY: "đang thử lại theo cách tương tự vì lỗi có vẻ tạm thời",
}


class PlanReflector:
    """Inspect execution results and turn them into a natural-language summary."""

    def reflect(self, goal: str, execution: ExecutionResult) -> ReflectionResult:
        if execution.completed:
            return ReflectionResult(status="completed", summary=f"Xong rồi, tôi đã hoàn thành: {goal}.")

        if execution.error_decision is not None:
            phrasing = _DECISION_PHRASING.get(execution.error_decision, "gặp lỗi")
            step_name = execution.failed_step.tool if execution.failed_step else ""
            reason = execution.failure_reason or "không rõ nguyên nhân"
            status = "aborted" if execution.error_decision == ErrorDecision.ABORT else "failed"
            action_note = " cần đổi mục tiêu hoặc cách thực hiện." if execution.error_decision == ErrorDecision.REPLAN else " cần xem lại điều kiện thực thi."
            summary = (
                f"Tôi đã thử thực hiện '{goal}', nhưng {phrasing}"
                + (f" ở bước '{step_name}'" if step_name else "")
                + f". Nguyên nhân: {reason}."
                + action_note
            )
            return ReflectionResult(status=status, summary=summary)

        if execution.failure_reason:
            return ReflectionResult(status="failed", summary=f"Tôi chưa hoàn thành được '{goal}' vì: {execution.failure_reason}.")

        return ReflectionResult(status="partial", summary=f"Hành động '{goal}' chưa hoàn tất, nhưng tôi đang giữ lại tiến độ hiện tại.")
