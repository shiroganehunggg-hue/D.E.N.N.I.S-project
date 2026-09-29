from __future__ import annotations

import json
import logging
import re
from typing import Any, Dict, List

from src.core.planner.models import Plan, PlanStep
from src.core.planner.plan import PlanParser
from src.providers.provider_result import ProviderResult
from src.tools.manager import ToolManager

logger = logging.getLogger(__name__)


class Planner:
    """Generate a full execution plan from a request without emitting step-by-step tool calls."""

    def __init__(self, tool_manager: ToolManager, llm_router: Any):
        self.tool_manager = tool_manager
        self.llm_router = llm_router

    def _tool_descriptions(self) -> List[str]:
        tool_descriptions: List[str] = []
        for schema in self.tool_manager.get_schemas():
            props = schema.get("parameters", {}).get("properties", {})
            prop_names = ", ".join(props.keys())
            tool_descriptions.append(f"- {schema['name']}: {schema['description']} | args: {prop_names}")
        return tool_descriptions

    def create_plan(self, user_request: str, memory_summary: str = "", context: str = "") -> Plan:
        tool_descriptions = self._tool_descriptions()

        prompt = {
            "role": "system",
            "content": (
                "Bạn là planner của DENNIS. Trả về CHỈ JSON hợp lệ, không có markdown, không có giải thích.\n"
                "Không bao giờ viết TOOL_CALL, không bao giờ trả lời tự nhiên.\n"
                "Chỉ dùng tool và argument có thật trong danh sách.\n"
                "Không invent tool name, không invent argument name, không dùng placeholder.\n"
                "Sinh kế hoạch tối thiểu cần thiết, không thêm bước thừa.\n"
                "Ví dụ cấu trúc:\n"
                '{"goal":"Open YouTube in Chrome","steps":[{"tool":"browser","args":{"action":"launch_browser"},"retries":1},{"tool":"browser","args":{"action":"open_url","url":"https://youtube.com"},"retries":1}]}'
                "\nNếu yêu cầu là TÌM KIẾM/TRA một từ khóa trên Google VÀ đọc/thu thập kết quả, dùng action "
                "\"search_google\" với argument \"query\" là từ khóa (KHÔNG url-encode, tool tự xử lý). Tool này trả về "
                "sẵn nội dung text thật của trang kết quả để bạn đọc, không cần bước gõ phím hay Enter riêng. Ví dụ:\n"
                '{"goal":"Mở Chrome và tra NASA","steps":[{"tool":"browser","args":{"action":"launch_browser"},"retries":1},{"tool":"browser","args":{"action":"search_google","query":"NASA"},"retries":1}]}'
                "\nNếu chỉ cần MỞ một trang cụ thể (không cần đọc nội dung), dùng open_url với URL đầy đủ như ví dụ "
                "YouTube ở trên. Muốn mở thêm tab mới (giữ tab hiện tại) thay vì điều hướng đè lên tab đang có, dùng "
                "action \"new_tab\" (có thể kèm url). Muốn đọc nội dung trang đang mở (không phải tìm kiếm), dùng "
                "action \"get_page_text\" (không cần argument khác).\n"
                "\nNếu người dùng nói tên profile/tài khoản Chrome cụ thể (vd 'profile công việc', 'tài khoản cá nhân', "
                "'profile Default'), thêm argument \"profile\" vào MỌI step dùng tool browser trong plan, với giá trị "
                "đúng y như cụm từ người dùng nói (giữ nguyên tiếng Việt, không dịch, không viết hoa/thường khác đi) "
                "để tool tự tra bảng ánh xạ sang đúng thư mục profile thật. Nếu người dùng KHÔNG nói tên profile nào, "
                "KHÔNG thêm argument \"profile\" (để tool tự dùng profile mặc định). Ví dụ:\n"
                '{"goal":"Mở Chrome profile công việc và tra NASA","steps":['
                '{"tool":"browser","args":{"action":"launch_browser","profile":"công việc"},"retries":1},'
                '{"tool":"browser","args":{"action":"open_url","url":"https://www.google.com/search?q=NASA","profile":"công việc"},"retries":1}]}'
                "\nDanh sách tool có sẵn:\n"
                + "\n".join(tool_descriptions)
                + "\n\nYêu cầu người dùng:\n"
                + user_request
                + "\n\nTóm tắt bộ nhớ:\n"
                + memory_summary
                + "\n\nContext:\n"
                + context
            ),
        }

        try:
            raw = self.llm_router.generate([prompt])
            if not raw:
                raise ValueError("Planner returned empty output")
            payload = self._extract_json(raw)
            plan = PlanParser.from_dict(payload)
            return self._validate_plan(plan, user_request)
        except Exception as exc:
            logger.exception("Planner failed: %s", exc)
            return self._fallback_plan(user_request)

    def replan(
        self,
        goal: str,
        tool_results: list,
        failed_step,
        failure_reason: str,
        memory_summary: str = "",
    ) -> Plan:
        tool_descriptions = self._tool_descriptions()

        successful_steps = []
        for result in tool_results or []:
            if getattr(result, "success", False):
                successful_steps.append(f"- {getattr(result, 'tool', 'unknown')}: {getattr(result, 'result', '') or getattr(result, 'error', '') or 'no output'}")

        failed_tool = getattr(failed_step, "tool", "unknown")
        failed_args = getattr(failed_step, "args", {}) or {}
        failed_header = (
            "- Bước thất bại: tool = {tool}\n"
            "  args = {args}\n"
            "  lý do thất bại = {reason}"
        ).format(tool=failed_tool, args=failed_args, reason=failure_reason or "Không rõ nguyên nhân")

        prompt = {
            "role": "system",
            "content": (
                "Bạn là planner của DENNIS đang làm REPLAN sau khi kế hoạch trước đã thất bại giữa chừng. "
                "Đây KHÔNG phải là tạo plan từ đầu.\n"
                "Hãy chỉ sinh các bước CÒN LẠI cần làm để hoàn thành goal ban đầu; không lặp lại các bước đã thành công.\n"
                "Không lặp lại y hệt bước vừa thất bại. Hãy đổi tool, đổi args hoặc đổi chiến lược nếu cần.\n"
                "Chỉ dùng tool có thật trong danh sách. JSON thuần, không markdown, không giải thích.\n"
                "Cấu trúc bắt buộc: {\"goal\": ..., \"steps\": [...]}\n"
                "Các bước đã thành công:\n"
                + ("\n".join(successful_steps) if successful_steps else "- Không có bước nào thành công trước đó.")
                + "\n\n"
                + failed_header
                + "\n\nDanh sách tool có sẵn:\n"
                + "\n".join(tool_descriptions)
                + "\n\nTóm tắt bộ nhớ:\n"
                + memory_summary
                + "\n\nGoal gốc:\n"
                + goal
                + "\n\nYêu cầu: trả về chỉ các bước còn lại cần làm để hoàn thành goal, không thêm lý do, không giải thích."
            ),
        }

        try:
            raw = self.llm_router.generate([prompt])
            if not raw:
                raise ValueError("Replan output is empty")
            payload = self._extract_json(raw)
            plan = PlanParser.from_dict(payload)
            return self._validate_plan(plan, goal)
        except Exception as exc:
            logger.exception("Planner replan failed: %s", exc)
            return self._fallback_plan(goal)

    def _extract_json(self, payload: str | ProviderResult) -> Dict[str, Any]:
        if isinstance(payload, ProviderResult):
            if not payload.success:
                raise ValueError(payload.error or "Planner provider request failed")
            payload = payload.content

        if not isinstance(payload, str):
            raise ValueError("Planner output is not a string")

        cleaned = payload.strip()
        if cleaned.startswith("```"):
            cleaned = re.sub(r"^```(?:json)?\s*", "", cleaned)
            cleaned = re.sub(r"\s*```$", "", cleaned)
        match = re.search(r"\{.*\}", cleaned, re.S)
        if not match:
            raise ValueError("No JSON object found")

        return json.loads(match.group(0))

    def _validate_plan(self, plan: Plan, user_request: str) -> Plan:
        allowed_tools = {schema["name"] for schema in self.tool_manager.get_schemas()}
        allowed_args = {schema["name"]: set(schema.get("parameters", {}).get("properties", {}).keys()) for schema in self.tool_manager.get_schemas()}

        valid_steps = []
        for step in plan.steps:
            if not step.tool or step.tool not in allowed_tools:
                continue
            invalid_args = [k for k in step.args.keys() if k not in allowed_args.get(step.tool, set())]
            if invalid_args:
                continue
            if step.tool.startswith("{{") or step.tool.endswith("}}"):
                continue
            valid_steps.append(step)

        if not valid_steps or not plan.goal:
            return self._fallback_plan(user_request)

        # Trước đây giới hạn cứng 3 bước làm mất âm thầm các bước cuối
        # (vd: bước "press_key Enter" để submit tìm kiếm), khiến hành động
        # coi như "thành công" nhưng thực chất chưa hoàn tất. Nâng giới
        # hạn lên và log rõ khi có bước bị cắt để dễ debug hơn.
        max_steps = 8
        if len(valid_steps) > max_steps:
            logger.warning(
                "Planner produced %d steps, truncating to %d: dropped steps=%s",
                len(valid_steps), max_steps, valid_steps[max_steps:],
            )
        return Plan(goal=plan.goal or "Plan", steps=valid_steps[:max_steps])

    def _fallback_plan(self, user_request: str) -> Plan:
        lowered = user_request.lower().strip()

        if "ctrl shift p" in lowered or "control shift p" in lowered:
            return Plan(goal=user_request, steps=[PlanStep(tool="hotkey", args={"keys": ["ctrl", "shift", "p"]}, retries=1)])

        if "press space" in lowered or "nhấn space" in lowered:
            return Plan(goal=user_request, steps=[PlanStep(tool="press_key", args={"key": "space"}, retries=1)])

        if "type" in lowered or "gõ" in lowered or "write" in lowered:
            extracted = re.search(r'"([^"]+)"', user_request)
            text_value = extracted.group(1) if extracted else user_request.split(" ", 1)[-1].strip()
            if text_value.lower() in {"hello world", "hello"}:
                text_value = "Hello World"
            return Plan(goal=user_request, steps=[PlanStep(tool="type_text", args={"text": text_value}, retries=1)])

        if "chrome" in lowered or "google chrome" in lowered or "youtube" in lowered:
            if "open" in lowered or "mở" in lowered or "url" in lowered or "youtube" in lowered:
                url = "https://youtube.com" if "youtube" in lowered else "https://www.google.com"
                return Plan(goal=user_request, steps=[PlanStep(tool="browser", args={"action": "launch_browser"}, retries=1), PlanStep(tool="browser", args={"action": "open_url", "url": url}, retries=1)])
            return Plan(goal=user_request, steps=[PlanStep(tool="browser", args={"action": "launch_browser"}, retries=1)])

        if "spotify" in lowered:
            play_intent = any(k in lowered for k in ["play", "phát", "nghe", "song", "track", "bài hát", "nhạc"])
            search_intent = any(k in lowered for k in ["search", "find", "tìm"])
            action = "play" if play_intent else "search" if search_intent else "open"
            query = user_request if action in {"play", "search"} else ""
            if action in {"play", "search"}:
                query = re.sub(
                    r"\b(?:please|can you|could you|play|listen to|search for|find|mở|phát|nghe|tìm(?: kiếm)?)\b",
                    " ",
                    query,
                    flags=re.IGNORECASE,
                )
                query = re.sub(
                    r"\b(?:spotify|on|in|trên|bài hát|bài|song|track|music|nhạc)\b",
                    " ",
                    query,
                    flags=re.IGNORECASE,
                )
                query = " ".join(query.split()).strip(" ,.!?-")
            args = {"action": action}
            if query:
                args["query"] = query
            return Plan(goal=user_request, steps=[PlanStep(tool="spotify", args=args, retries=1)])

        if "vscode" in lowered or "visual studio code" in lowered or "code" in lowered:
            return Plan(goal=user_request, steps=[PlanStep(tool="launch_app", args={"app_name_or_path": "code"}, retries=1), PlanStep(tool="focus_window", args={"process_name": "code.exe"}, retries=1)])

        if "notepad" in lowered:
            return Plan(goal=user_request, steps=[PlanStep(tool="launch_app", args={"app_name_or_path": "notepad"}, retries=1), PlanStep(tool="focus_window", args={"process_name": "notepad.exe"}, retries=1)])

        return Plan(goal=user_request, steps=[PlanStep(tool="launch_app", args={"app_name_or_path": "notepad"}, retries=1)])