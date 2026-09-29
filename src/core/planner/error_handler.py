from __future__ import annotations

import json
import logging
import re
from typing import Any, Dict

from src.core.planner.models import ErrorAnalysis, ErrorDecision, PlanStep
from src.providers.provider_result import ProviderResult

logger = logging.getLogger(__name__)


ERROR_ANALYST_PROMPT = (
    "Bạn là module phân tích lỗi của DENNIS. Một bước trong kế hoạch vừa thất bại.\n"
    "Dựa trên tool, tham số và lỗi bên dưới, hãy chọn CHÍNH XÁC MỘT trong 4 hướng xử lý:\n"
    "- retry: lỗi có vẻ tạm thời (timeout mạng, cửa sổ chưa load kịp, file đang bị khoá, "
    "race condition) — thử lại đúng bước này nhiều khả năng sẽ thành công.\n"
    "- skip: bước này không quan trọng với mục tiêu chung, có thể bỏ qua mà vẫn coi là "
    "hoàn thành được việc chính.\n"
    "- replan: cách tiếp cận hiện tại sai (sai tool, sai tham số, sai giả định), cần một "
    "kế hoạch khác cho phần việc còn lại.\n"
    "- abort: mục tiêu không thể thực hiện được hoặc tiếp tục thử sẽ không an toàn/không "
    "hợp lý.\n\n"
    "Trả về CHỈ JSON hợp lệ, không markdown, không giải thích gì thêm ngoài JSON:\n"
    '{"decision":"retry|skip|replan|abort","reason":"vì sao thất bại, 1 câu ngắn",'
    '"user_message":"câu ngắn báo cho người dùng, tối đa 15 từ, tiếng Việt, xưng hô như DENNIS"}'
)


class ErrorAnalyzer:
    """Turns a failed plan step + its error into a recovery decision using an LLM.

    Sits between PlanExecutor (which runs steps) and PlanReflector (which
    summarizes the outcome). Replaces blind "retry N times then give up"
    behaviour with a decision that also considers whether the step is
    critical, whether the error looks transient, and whether the whole
    approach should change instead.
    """

    def __init__(self, llm_router: Any):
        self.llm_router = llm_router

    def analyze(
        self,
        step: PlanStep,
        error: str,
        attempt: int,
        max_attempts: int,
    ) -> ErrorAnalysis:
        heuristics = self._heuristic_decision(step, error)
        if heuristics is not None:
            decision, reason, user_message = heuristics
            logger.info(
                "[ErrorHandler] %s -> %s via heuristic (%s)",
                step.tool,
                decision.value,
                reason or "no reason",
            )
            return ErrorAnalysis(decision=decision, reason=reason, user_message=user_message)

        # Luôn hỏi LLM, kể cả khi đây là lần thử cuối (attempt >= max_attempts):
        # dù không còn lượt "retry" nào nữa, "skip" hay "abort" vẫn là quyết
        # định hợp lệ và cần LLM cân nhắc — ép sẵn sang replan ở đây sẽ chặn
        # mất cơ hội skip một bước không quan trọng chỉ vì step.retries=0.
        prompt = {
            "role": "system",
            "content": (
                ERROR_ANALYST_PROMPT
                + "\n\nTool: " + step.tool
                + "\nArgs: " + json.dumps(step.args, ensure_ascii=False)
                + f"\nCritical: {step.critical}"
                + f"\nLần thử: {attempt}/{max_attempts}"
                + "\nLỗi:\n" + error[:500]
            ),
        }

        try:
            raw = self.llm_router.generate([prompt])
            payload = self._extract_json(raw)
            decision = ErrorDecision(str(payload.get("decision", "replan")).lower().strip())
        except Exception as exc:
            logger.exception("[ErrorHandler] Phân tích lỗi thất bại: %s — mặc định replan", exc)
            return ErrorAnalysis(
                decision=ErrorDecision.REPLAN,
                reason=str(exc),
                user_message="Gặp sự cố khi phân tích lỗi, đang điều chỉnh cách làm, sếp.",
            )

        reason = str(payload.get("reason", "")) if isinstance(payload, dict) else ""
        user_message = str(payload.get("user_message", "")) if isinstance(payload, dict) else ""

        # Bước quan trọng thì không được phép âm thầm skip — ép lên replan.
        if step.critical and decision == ErrorDecision.SKIP:
            decision = ErrorDecision.REPLAN
            reason = reason or "Bước quan trọng, không thể bỏ qua"
            user_message = user_message or "Bước này quan trọng, đang tìm cách khác, sếp."

        logger.info(
            "[ErrorHandler] %s -> %s (%s)", step.tool, decision.value, reason or "no reason"
        )
        return ErrorAnalysis(decision=decision, reason=reason, user_message=user_message)

    def _heuristic_decision(self, step: PlanStep, error: str) -> tuple[ErrorDecision, str, str] | None:
        if not error:
            return None

        text = error.lower()
        app_name = str(step.args.get("app_name_or_path") or "").strip()

        path_missing_patterns = (
            "the system cannot find the file specified",
            "application not found",
            "file not found",
            "cannot find the file",
            "not found",
            "no such file or directory",
            "__missing__",
        )
        is_missing_target = any(pattern in text for pattern in path_missing_patterns)
        if step.tool in {"launch_app", "open_app"} and (is_missing_target or not app_name):
            return (
                ErrorDecision.REPLAN,
                "Ứng dụng hoặc đường dẫn sai; cần đổi cách mở hoặc chọn mục tiêu khác.",
                "App không tồn tại hoặc đường dẫn sai, đang tìm cách mở khác, sếp.",
            )

        if "access is denied" in text or "permission denied" in text:
            return (
                ErrorDecision.ABORT,
                "Không đủ quyền để thực hiện hành động này.",
                "Mình không có quyền thực hiện bước này.",
            )

        if "timeout" in text or "temporar" in text or "timed out" in text:
            return (
                ErrorDecision.RETRY,
                f"Lỗi timeout/tạm thời: {error[:180]}",
                "Đang thử lại bước này vì lỗi có vẻ tạm thời.",
            )

        if "window" in text and "not found" in text:
            return (
                ErrorDecision.REPLAN,
                "Cửa sổ mục tiêu không tồn tại hoặc đã thay đổi; cần định vị lại.",
                "Cửa sổ đã biến mất hoặc thay đổi, đang định vị lại.",
            )

        return None

    def _extract_json(self, payload: str | ProviderResult) -> Dict[str, Any]:
        if isinstance(payload, ProviderResult):
            if not payload.success:
                raise ValueError(payload.error or "Error analyzer provider request failed")
            payload = payload.content

        if not isinstance(payload, str):
            raise ValueError("Error analyzer trả về output không phải string")

        cleaned = payload.strip()
        if cleaned.startswith("```"):
            cleaned = re.sub(r"^```(?:json)?\s*", "", cleaned)
            cleaned = re.sub(r"\s*```$", "", cleaned)
        match = re.search(r"\{.*\}", cleaned, re.S)
        if not match:
            raise ValueError("Không tìm thấy JSON object trong output của error analyzer")

        return json.loads(match.group(0))
