import json
import os
import time
from pathlib import Path
from typing import List, Optional, Any

from openai import OpenAI

from src.core.key_manager import KeyManager
from src.core.logger import logger
from src.config.settings import Settings
from src.providers.base import AIProvider
from src.providers.provider_result import ProviderResult


class SchemaRequestError(Exception):
    """Raised when the request schema (tools= payload) is invalid for the provider."""
    pass


class OpenAICompatibleProvider(AIProvider):

    # By default, providers based on the OpenAI-compatible client are
    # assumed to support native tool-calling via a `tools` parameter.
    supports_tool_calling_native = True

    api_key_env = ""
    keys_file = ""
    base_url = ""
    model = ""
    extra_params = {}  # override in subclass, vd: {"reasoning_format": "parsed"}

    def __init__(self):
        super().__init__()

        self.key_manager: KeyManager = KeyManager()
        self.client: Optional[OpenAI] = None

        self._load_keys()

    def _default_keys_file(self) -> str:
        """
        Automatically infer:
        GROQ_API_KEY      -> src/config/groq_keys.json
        HF_API_KEY        -> src/config/hf_keys.json
        MISTRAL_API_KEY   -> src/config/mistral_keys.json
        """
        if self.keys_file:
            return self.keys_file

        if not self.api_key_env:
            return ""

        provider = self.api_key_env.lower().replace("_api_key", "")
        return f"src/config/{provider}_keys.json"

    def _load_keys(self) -> None:

        keys_file = self._default_keys_file()

        resolved_path = None

        if keys_file:
            candidate = Path(keys_file)

            if not candidate.is_absolute():
                base_dirs = [
                    Path(__file__).resolve().parents[2],
                    Path(__file__).resolve().parents[1],
                ]

                for base_dir in base_dirs:
                    test_path = base_dir / candidate
                    if test_path.exists():
                        resolved_path = test_path
                        break

                if resolved_path is None:
                    resolved_path = base_dirs[0] / candidate

            else:
                resolved_path = candidate

        if resolved_path and resolved_path.exists():

            self.key_manager = KeyManager.from_json(str(resolved_path))

        elif self.api_key_env:

            api_key = os.getenv(self.api_key_env)

            if api_key:
                self.key_manager = KeyManager([api_key])

        if self.key_manager.total_count() > 0:
            self._create_client()
        else:
            self.client = None

    def _create_client(self) -> None:

        current_key = self.key_manager.current_key()

        if current_key is None:
            self.client = None
            return

        self.client = OpenAI(
            api_key=current_key,
            base_url=self.base_url,
            timeout=Settings.PROVIDER_TIMEOUT_SECONDS,
            max_retries=0,
        )

    def _next_key(self) -> None:
        self.key_manager.next_key()
        self._create_client()

    def _should_rotate(self, error: str) -> bool:

        if self.key_manager.total_count() <= 1:
            return False

        lowered = error.lower()

        keywords = (
            "429",
            "rate limit",
            "resource_exhausted",
            "quota",
            "insufficient_quota",
            "payment_required",
            "401",
            "403",
            "unauthorized",
            "forbidden",
        )

        return any(keyword in lowered for keyword in keywords)

    def _attempt_request(self, messages: List[dict], tools: list[dict] | None = None):

        # Pass `tools` directly when the underlying client supports native
        # tool-calling. `extra_body` is kept for provider-specific params.
        kwargs: dict[str, Any] = dict(model=self.model, messages=messages, extra_body=self.extra_params)
        if tools:
            kwargs["tools"] = tools

            # Log raw payload when debugging to help diagnose schema errors.
            if getattr(Settings, "DEBUG", False):
                try:
                    logger.provider(type(self).__name__, f"TOOLS_PAYLOAD: {json.dumps(kwargs['tools'], ensure_ascii=False)[:1000]}")
                except Exception:
                    logger.provider(type(self).__name__, f"TOOLS_PAYLOAD (non-json) len={len(str(kwargs['tools']))}")

        return self.client.chat.completions.create(**kwargs)

    def generate(self, messages, tools: list[dict] | None = None):

        if self.client is None:
            return ProviderResult(
                success=False,
                error="Missing API key(s)",
                provider=type(self).__name__,
            )

        start = time.perf_counter()

        attempts = max(1, self.key_manager.total_count())

        for _ in range(attempts):

            try:

                response = self._attempt_request(messages, tools=tools)

                print("RAW MESSAGE:", repr(response.choices[0].message))
                print("RAW CONTENT:", repr(response.choices[0].message.content))
                print("RAW TOOL_CALLS:", repr(response.choices[0].message.tool_calls))

                elapsed = time.perf_counter() - start

                message = response.choices[0].message

                # If the model returned native tool calls, normalize their
                # structure. SDKs differ: some expose `tool_calls` as a list,
                # others expose a single `tool_call` or `function_call`.
                raw_tool_calls = []
                if hasattr(message, "tool_calls"):
                    raw_tool_calls = message.tool_calls or []
                elif hasattr(message, "tool_call"):
                    raw_tool_calls = [message.tool_call]
                elif hasattr(message, "function_call"):
                    raw_tool_calls = [message.function_call]
                elif isinstance(message, dict):
                    raw_tool_calls = message.get("tool_calls") or []
                    if not raw_tool_calls:
                        raw_tool_calls = [message.get("tool_call") or message.get("function_call")]
                    raw_tool_calls = [tc for tc in raw_tool_calls if tc is not None]

                if raw_tool_calls:
                    normalized_tool_calls = []
                    for raw_tool_call in raw_tool_calls:
                        name = None
                        args = {}
                        tool_call_id = None

                        if isinstance(raw_tool_call, dict):
                            tool_call_id = raw_tool_call.get("id")
                            if "name" in raw_tool_call and "args" in raw_tool_call:
                                name = raw_tool_call.get("name")
                                args = raw_tool_call.get("args") or {}
                            else:
                                func = raw_tool_call.get("function") or {}
                                if isinstance(func, dict):
                                    name = func.get("name") or func.get("title")
                                    arguments = func.get("arguments")
                                    if isinstance(arguments, str):
                                        try:
                                            args = json.loads(arguments)
                                        except Exception:
                                            args = {}
                                    else:
                                        args = arguments or {}
                        else:
                            tool_call_id = getattr(raw_tool_call, "id", None)
                            func = getattr(raw_tool_call, "function", None)
                            if func is not None:
                                name = getattr(func, "name", None)
                                arguments = getattr(func, "arguments", None)
                            else:
                                name = getattr(raw_tool_call, "name", None)
                                arguments = getattr(raw_tool_call, "arguments", None)

                            if isinstance(arguments, str):
                                try:
                                    args = json.loads(arguments)
                                except Exception:
                                    args = {}
                            else:
                                args = arguments or {}

                        if not isinstance(args, dict):
                            args = {}

                        normalized_tool_calls.append({
                            "id": tool_call_id or "call_unknown",
                            "type": "function",
                            "function": {
                                "name": name,
                                "arguments": json.dumps(args, ensure_ascii=False),
                            },
                        })

                    return ProviderResult(
                        success=True,
                        content="",
                        tool_calls=normalized_tool_calls,
                        provider=type(self).__name__,
                        latency=elapsed,
                    )

                text = getattr(message, "content", None) or (message.get("content") if isinstance(message, dict) else "")
                reasoning_text = getattr(message, "reasoning_content", "") or ""

                return ProviderResult(
                    success=True,
                    content=str(text).strip(),
                    reasoning=reasoning_text.strip() if reasoning_text else "",
                    provider=type(self).__name__,
                    latency=elapsed,
                )

            except Exception as exc:

                error_text = str(exc)

                # If the exception indicates the request schema (tools=) is
                # invalid for this provider, raise SchemaRequestError so we
                # do NOT rotate API keys and surface a clear request error.
                schema_error_indicators = (
                    "tools.0.type",
                    "tools.0.name",
                    "Field required",
                    "is unsupported",
                    "unsupported property",
                    "invalid request",
                )

                lowered = error_text.lower() if error_text else ""
                if any(ind.lower() in lowered for ind in schema_error_indicators):
                    raise SchemaRequestError(error_text)

                if self._should_rotate(error_text):
                    self._next_key()
                    continue

                elapsed = time.perf_counter() - start

                return ProviderResult(
                    success=False,
                    error=error_text,
                    provider=type(self).__name__,
                    latency=elapsed,
                )

        elapsed = time.perf_counter() - start

        return ProviderResult(
            success=False,
            error="All API keys exhausted.",
            provider=type(self).__name__,
            latency=elapsed,
        )