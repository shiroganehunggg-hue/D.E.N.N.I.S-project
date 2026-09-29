from src.config.settings import Settings
from src.personality.prompt import SYSTEM_PROMPT


class ResponseBuilder:
    """
    Chịu trách nhiệm xây toàn bộ prompt gửi cho LLM.

    Thứ tự:

    System Prompt
            ↓
    Long-term Memory
            ↓
    Conversation Summary
            ↓
    Recent History
            ↓
    Current User Message
    """

    def __init__(
        self,
        history_limit: int = Settings.HISTORY_LIMIT,
    ):
        self.history_limit = history_limit

    def build(
        self,
        memory,
        user_prompt: str,
    ):

        messages = []

        # ---------------------------------------------------
        # 1. Personality
        # ---------------------------------------------------

        messages.append(
            {
                "role": "system",
                "content": SYSTEM_PROMPT,
            }
        )

        # ---------------------------------------------------
        # 2. Long-term facts (chỉ lấy facts liên quan tới câu hỏi hiện tại)
        # ---------------------------------------------------

        relevant_facts = memory.get_relevant_facts(user_prompt)

        if relevant_facts:

            facts = "\n".join(
                f"- {fact}"
                for fact in relevant_facts
            )

            messages.append(
                {
                    "role": "system",
                    "content":
                        "Long-term memory about the user:\n\n"
                        + facts
                }
            )

        # ---------------------------------------------------
        # 3. Conversation summary
        # ---------------------------------------------------

        summary = memory.summary.get("text", "").strip()

        if summary:

            messages.append(
                {
                    "role": "system",
                    "content":
                        "Summary of previous conversations:\n\n"
                        + summary
                }
            )

        # ---------------------------------------------------
        # 4. Recent history
        # ---------------------------------------------------

        history = memory.get_recent_messages(
            self.history_limit
        )

        messages.extend(history)

        # ---------------------------------------------------
        # 5. Current user message
        # ---------------------------------------------------

        # Nếu history chưa chứa câu vừa nhập
        if (
            not history
            or history[-1]["role"] != "user"
            or history[-1]["content"] != user_prompt
        ):

            messages.append(
                {
                    "role": "user",
                    "content": user_prompt,
                }
            )

        return messages