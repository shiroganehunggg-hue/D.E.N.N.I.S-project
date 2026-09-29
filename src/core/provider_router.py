import time
from typing import List

from src.core.logger import logger
from src.core.metrics import ProviderMetrics
from src.core.provider_score import ProviderScore
from src.config.settings import Settings
from src.providers.provider_result import ProviderResult

DEFAULT_PROVIDER_ORDER = [
    "HuggingFaceProvider",
    "MistralProvider",
    "GroqProvider",
    "OpenRouterProvider",
    "NvidiaProvider",
    "GeminiProvider",
    "CohereProvider",
]

REASONING_KEYWORDS = (
    "tính", "chứng minh", "giải phương trình", "mômen", "momen",
    "đạo hàm", "tích phân", "lực", "vận tốc", "gia tốc", "xác suất",
    "code", "debug", "hàm số", "bài toán", "định luật", "vật lý", "vật lí",
)


def classify_task(messages: List[dict]) -> str:
    """
    Heuristic đơn giản: quét tin nhắn cuối của user, tìm từ khóa
    reasoning-heavy. Có thể nâng cấp sau bằng cách gọi 1 model nhỏ
    để classify chính xác hơn.
    """
    if not messages:
        return "general"

    last_user_msg = ""
    for msg in reversed(messages):
        if msg.get("role") == "user":
            last_user_msg = msg.get("content", "")
            break

    lowered = last_user_msg.lower()

    if any(keyword in lowered for keyword in REASONING_KEYWORDS):
        return "reasoning_heavy"

    return "general"


class ProviderRouter:
    """
    Router thông minh.

    - Giữ provider hiện tại nếu còn hoạt động.
    - Chỉ chuyển khi provider lỗi.
    - Ưu tiên provider reasoning khi task được phân loại reasoning_heavy.
    - Ưu tiên Mistral khi task nhẹ (general).
    """

    def __init__(
        self,
        providers: List,
        metrics: ProviderMetrics | None = None,
    ):
        self.providers = providers
        self.current_index = 0
        self.metrics = metrics or ProviderMetrics()
        self.scorer = ProviderScore(self.metrics)

    @property
    def current(self):
        return self.providers[self.current_index]

    def _rank_by_score_or_default(self):

        ranked_providers = list(self.providers)

        scores = [
            self.scorer.score(provider.__class__.__name__)
            for provider in ranked_providers
        ]

        if any(score != 0 for score in scores):
            ranked_indexes = sorted(
                range(len(ranked_providers)),
                key=lambda index: scores[index],
                reverse=True,
            )
            ranked_providers = [
                ranked_providers[index] for index in ranked_indexes
            ]
        else:
            provider_names = {
                provider.__class__.__name__: provider
                for provider in ranked_providers
            }
            default_ranked = [
                provider_names[name]
                for name in DEFAULT_PROVIDER_ORDER
                if name in provider_names
            ]
            if default_ranked:
                ranked_providers = default_ranked

        not_in_cooldown = [
            provider for provider in ranked_providers
            if not self.metrics.is_in_cooldown(provider.__class__.__name__)
        ]
        in_cooldown = [
            provider for provider in ranked_providers
            if self.metrics.is_in_cooldown(provider.__class__.__name__)
        ]

        return not_in_cooldown + in_cooldown

    def _prioritize_by_task(self, task_type, ranked_providers):

        if task_type == "reasoning_heavy":

            reasoning_providers = [
                p for p in ranked_providers
                if getattr(p, "is_reasoning_model", False)
            ]
            other_providers = [
                p for p in ranked_providers
                if not getattr(p, "is_reasoning_model", False)
            ]

            logger.router(
                f"Task classified as reasoning_heavy -> prioritizing: "
                f"{[p.__class__.__name__ for p in reasoning_providers]}"
            )

            return reasoning_providers + other_providers

        else:

            mistral_providers = [
                p for p in ranked_providers
                if p.__class__.__name__ == "MistralProvider"
            ]
            other_providers = [
                p for p in ranked_providers
                if p.__class__.__name__ != "MistralProvider"
            ]

            logger.router("Task classified as general -> prioritizing Mistral")

            return mistral_providers + other_providers

    def generate(self, messages, tools: list[dict] | None = None, tool_system_message: dict | None = None):

        configured_providers = [
            provider for provider in self.providers
            if getattr(provider, "client", None) is not None
        ]

        if not configured_providers:
            return ProviderResult(
                success=False,
                content="Không có provider nào được cấu hình với API key hợp lệ.",
                error="No configured providers available.",
                provider="ProviderRouter",
                latency=0.0,
            )

        total = len(configured_providers)

        last_error = "Unknown error"

        task_type = classify_task(messages)

        ranked_providers = self._rank_by_score_or_default()
        ranked_providers = [
            provider for provider in ranked_providers
            if getattr(provider, "client", None) is not None
        ]

        ranked_providers = self._prioritize_by_task(task_type, ranked_providers)

        start_index = self.current_index % total

        max_attempts = min(total, Settings.PROVIDER_MAX_ATTEMPTS)
        for attempt in range(max_attempts):

            provider = ranked_providers[(start_index + attempt) % total]
            attempt_start = time.perf_counter()

            try:

                # Determine whether to pass schemas via `tools` (native) or
                # to append the textual system message (fallback). We treat
                # providers as supporting native tool-calls by default; a
                # provider can set `supports_tool_calling_native = False`
                # to opt-out.
                supports_native = getattr(provider, "supports_tool_calling_native", True)

                # If provider does not support native tools and a textual
                # tool system message was provided by caller, append it.
                messages_to_send = messages
                if not supports_native and tool_system_message:
                    # `tool_system_message` was supplied by caller; append it
                    # only for fallback providers that need textual fallback.
                    messages_to_send = list(messages) + [tool_system_message]

                try:
                    if supports_native:
                        result = provider.generate(messages_to_send, tools=tools)
                    else:
                        result = provider.generate(messages_to_send)
                except TypeError:
                    # Older providers may not accept the extra param;
                    # fall back to the single-arg call.
                    result = provider.generate(messages_to_send)

                if not isinstance(result, ProviderResult):
                    raise TypeError(
                        f"{type(provider).__name__} phải trả về ProviderResult."
                    )

                logger.info(f"\n===== {result.provider} =====")

                if result.success:
                    self.metrics.record_success(
                        result.provider,
                        result.latency,
                    )

                    logger.success(
                        f"SUCCESS ({result.latency:.2f}s)"
                    )

                    logger.info(repr(result.content))

                    logger.info("===================================")

                    logger.router(f"Using {result.provider}")

                    return result

                else:
                    self.metrics.record_failure(
                        result.provider,
                        result.latency,
                        error_message=result.error,
                    )

                    logger.warning(
                        f"FAILED ({result.latency:.2f}s)"
                    )

                    logger.warning(result.error)

                    logger.warning("===================================")

                    last_error = result.error

            except Exception as exc:

                last_error = str(exc)
                self.metrics.record_failure(
                    type(provider).__name__,
                    time.perf_counter() - attempt_start,
                    error_message=last_error,
                )

                logger.error(f"\n===== {type(provider).__name__} =====")
                logger.error(f"EXCEPTION: {exc}")
                logger.error("===================================")

            logger.router(f"{type(provider).__name__} failed -> switching...")

            self.current_index = (
                self.current_index + 1
            ) % total

        return ProviderResult(
            success=False,
            content=(
                "Tất cả provider đều lỗi.\n\n"
                f"Lỗi cuối:\n{last_error}"
            ),
            error=last_error,
            provider="ProviderRouter",
            latency=0.0,
        )
