import json

from src.core.logger import logger
from src.providers.groq_provider import GroqProvider
from src.providers.provider_result import ProviderResult

CLASSIFY_PROMPT = """Bạn là bộ phân loại câu nhập của người dùng cho trợ lý AI D.E.N.N.I.S. \
Đọc câu người dùng vừa gõ và trả về DUY NHẤT 1 JSON object (không giải thích, không markdown, không dấu ```), đúng format:

{{
  "intent": "chat" | "question" | "action" | "forget",
  "complexity": "simple" hoặc "complex",
  "fact": null hoặc "1 câu fact ngắn gọn nếu câu chứa thông tin cá nhân đáng nhớ lâu dài",
  "replace_fact": null hoặc "câu fact CŨ (copy nguyên văn từ danh sách bên dưới) cần bị xóa/thay thế vì đã lỗi thời hoặc mâu thuẫn với fact mới"
}}

Danh sách fact đã lưu về người dùng (nếu có):
{existing_facts}

Quy tắc:
- "forget" chỉ khi người dùng yêu cầu xóa/quên fact đã lưu.
- "action" chỉ khi người dùng yêu cầu thực hiện một nhiệm vụ hoặc thao tác trên máy tính: mở app, tìm kiếm, viết file, tạo project, click, gõ, chạy lệnh, gửi email, tạo kế hoạch, ...
- "question" khi người dùng hỏi kiến thức, tư vấn, suy nghĩ, ý kiến, hoặc lời giải thích mà không yêu cầu máy làm hành động cụ thể.
- "chat" khi là lời chào, nói chuyện đời thường, trạng thái, cảm xúc, câu chuyện, lời cảm ơn, hoặc nội dung không yêu cầu hành động hay kiến thức chuyên sâu.
- "complexity" = "complex" nếu cần suy luận nhiều bước, viết code, phân tích dài, kiến thức chuyên sâu. "simple" nếu chỉ chào hỏi/chat thường/hỏi ngắn.
- "fact" chỉ điền khi có thông tin CÁ NHÂN cụ thể MỚI hoặc THAY ĐỔI so với danh sách đã lưu.
- "replace_fact" chỉ điền khi fact mới thay thế fact cũ.

Câu người dùng: {text}"""


class InputClassifier:

    def __init__(self):
        self.provider = None

    def _get_provider(self):
        if self.provider is None:
            self.provider = GroqProvider()
        return self.provider

    def classify(self, user_input: str, existing_facts=None) -> dict:

        default = {
            "intent": "chat",
            "complexity": "simple",
            "fact": None,
            "replace_fact": None,
        }

        existing_facts = existing_facts or []

        facts_text = (
            "\n".join(
                f"- {fact['text']}"
                if isinstance(fact, dict)
                else f"- {fact}"
                for fact in existing_facts
            )
            if existing_facts
            else "(chưa có fact nào)"
        )

        messages = [
            {
                "role": "system",
                "content": "Bạn chỉ trả về JSON, không giải thích gì thêm.",
            },
            {
                "role": "user",
                "content": CLASSIFY_PROMPT.format(
                    text=user_input,
                    existing_facts=facts_text,
                ),
            },
        ]

        raw = None
        cleaned = None

        try:

            provider = self._get_provider()
            result: ProviderResult = provider.generate(messages)

            if not result.success:
                logger.warning(
                    f"[Classifier] Provider failed: {result.error}"
                )
                return default

            raw = result.content.strip()

            cleaned = (
                raw.removeprefix("```json")
                .removeprefix("```")
                .removesuffix("```")
                .strip()
            )

            data = json.loads(cleaned)

            logger.info("[Classifier] Parsed successfully")

            intent = str(data.get("intent", "chat") or "chat").lower()
            if intent not in {"chat", "question", "action", "forget"}:
                intent = "chat"
            return {
                "intent": intent,
                "complexity": data.get("complexity", "simple"),
                "fact": data.get("fact"),
                "replace_fact": data.get("replace_fact"),
            }

        except Exception as exc:

            logger.error(
                f"[Classifier] {exc} | raw={raw} | cleaned={cleaned}"
            )

            return default