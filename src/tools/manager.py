import ast
import time
from typing import Any, Dict, List

from src.core.planner.models import ToolResult
from src.tools.base import Tool

CONFIRMATION_REQUIRED_TOOLS = {"edit_file", "run_python", "write_file"}


class ToolManager:
    """Đăng ký và điều phối các Tool. Single responsibility: quản lý tool registry."""

    def __init__(self):
        self._tools: Dict[str, Tool] = {}
        self._approval_callback = None

    def set_approval_callback(self, callback) -> None:
        self._approval_callback = callback

    def register(self, tool: Tool) -> None:
        self._tools[tool.name] = tool

    def get_schemas(self) -> List[Dict[str, Any]]:
        return [t.schema() for t in self._tools.values()]

    def to_openai_tool_format(self) -> List[Dict[str, Any]]:
        """
        Convert internal flat tool schemas (name, description, parameters)
        into OpenAI-compatible tool descriptors expected by some APIs:
        {"type": "function", "function": { ...schema... }}

        Keep `get_schemas()` unchanged for textual fallback prompts.
        """
        converted = []
        for t in self._tools.values():
            schema = t.schema()
            converted.append({"type": "function", "function": schema})
        return converted

    def call(self, name: str, **kwargs) -> ToolResult:
        if name not in self._tools:
            return ToolResult(tool=name, success=False, error=f"Không tìm thấy tool '{name}'")
        if name in CONFIRMATION_REQUIRED_TOOLS:
            if self._approval_callback is None:
                return ToolResult(tool=name, success=False, error="This tool requires user confirmation.")
            try:
                approved = self._approval_callback(name, kwargs)
            except Exception as exc:
                return ToolResult(tool=name, success=False, error=f"User confirmation failed: {exc}")
            if not approved:
                return ToolResult(tool=name, success=False, error="User denied or did not confirm this action.")

        started = time.perf_counter()
        try:
            raw_result = self._tools[name].run(**kwargs)
        except Exception as exc:
            duration_ms = int((time.perf_counter() - started) * 1000)
            return ToolResult(tool=name, success=False, error=str(exc), duration_ms=duration_ms)

        duration_ms = int((time.perf_counter() - started) * 1000)
        return self._normalize_result(name, raw_result, duration_ms)

    def _normalize_mapping_result(self, name: str, raw_result: dict, duration_ms: int) -> ToolResult:
        return ToolResult(
            tool=name,
            success=bool(raw_result.get("success", False)),
            result=str(raw_result.get("result") or raw_result.get("message") or raw_result.get("text") or ""),
            data=raw_result.get("data", raw_result),
            error=raw_result.get("error"),
            duration_ms=duration_ms,
        )

    def _normalize_result(self, name: str, raw_result: Any, duration_ms: int) -> ToolResult:
        if isinstance(raw_result, ToolResult):
            return ToolResult(
                tool=raw_result.tool or name,
                success=raw_result.success,
                result=raw_result.result,
                data=raw_result.data,
                error=raw_result.error,
                duration_ms=raw_result.duration_ms if raw_result.duration_ms is not None else duration_ms,
                duration_seconds=(raw_result.duration_ms or duration_ms) / 1000.0 if raw_result.duration_seconds is None else raw_result.duration_seconds,
            )

        if isinstance(raw_result, dict):
            if "success" in raw_result:
                return self._normalize_mapping_result(name, raw_result, duration_ms)
            return ToolResult(
                tool=name,
                success=False,
                result=str(raw_result.get("result") or raw_result.get("message") or ""),
                data=raw_result,
                error=str(raw_result.get("error") or "Tool returned a mapping without an explicit success status."),
                duration_ms=duration_ms,
            )

        if isinstance(raw_result, str):
            try:
                parsed = ast.literal_eval(raw_result)
            except (ValueError, SyntaxError):
                parsed = None

            if isinstance(parsed, dict) and "success" in parsed:
                return self._normalize_mapping_result(name, parsed, duration_ms)

            if not raw_result.strip():
                return ToolResult(
                    tool=name,
                    success=False,
                    error="Tool returned an empty result without an explicit success status.",
                    duration_ms=duration_ms,
                )

            return ToolResult(tool=name, success=True, result=raw_result, data={"value": raw_result}, duration_ms=duration_ms)

        return ToolResult(tool=name, success=True, result=str(raw_result), data=raw_result, duration_ms=duration_ms)
