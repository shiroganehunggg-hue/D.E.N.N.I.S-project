import os
import time

from dotenv import load_dotenv
from google import genai

from src.config.settings import Settings
from src.core.logger import logger
from src.providers.base import AIProvider
from src.providers.provider_result import ProviderResult

load_dotenv()


class GeminiProvider(AIProvider):

    # Fallback provider: may not support native tool-calling.
    supports_tool_calling_native = False

    def __init__(self):
        self.client = None

        api_key = (
            os.getenv("GEMINI_API_KEY")
            or os.getenv("GOOGLE_API_KEY")
        )

        if api_key:
            self.client = genai.Client(api_key=api_key)

    def generate(self, messages, tools: list[dict] | None = None):

        start_time = time.perf_counter()

        if self.client is None:
            return ProviderResult(
                success=False,
                error="Vui lòng thiết lập GEMINI_API_KEY.",
                provider="Gemini",
                latency=time.perf_counter() - start_time,
            )

        prompt = []

        for msg in messages:
            role = msg.get("role", "user").upper()
            content = msg.get("content", "")
            prompt.append(f"[{role}]\n{content}")

        prompt = "\n\n".join(prompt)

        for attempt in range(Settings.PROVIDER_RETRY_COUNT):

            try:

                response = self.client.models.generate_content(
                    model=Settings.GEMINI_MODEL,
                    contents=prompt,
                )

                text = getattr(response, "text", "") or ""
                text = text.strip()

                if text:

                    latency = time.perf_counter() - start_time

                    logger.provider("Gemini", "Success")

                    return ProviderResult(
                        success=True,
                        content=text,
                        provider="Gemini",
                        latency=latency,
                    )

                logger.provider("Gemini", "Empty response")

            except Exception as exc:

                logger.provider(
                    "Gemini",
                    f"Attempt {attempt + 1} failed: {exc}",
                )

                if attempt == 1:
                    return ProviderResult(
                        success=False,
                        error=str(exc),
                        provider="Gemini",
                        latency=time.perf_counter() - start_time,
                    )

                time.sleep(Settings.PROVIDER_RETRY_DELAY)

        return ProviderResult(
            success=False,
            error="Gemini trả về phản hồi rỗng.",
            provider="Gemini",
            latency=time.perf_counter() - start_time,
        )
    