import json
import logging
import os

import numpy as np

SUMMARY_TRIGGER = 12       # short-term buffer vượt số này thì tóm tắt bớt
KEEP_RAW_AFTER_SUMMARY = 6  # giữ lại bao nhiêu tin gần nhất (nguyên văn) sau khi tóm tắt

EMBEDDING_MODEL_NAME = "all-MiniLM-L6-v2"

SIMILARITY_THRESHOLD = 0.35  # dưới ngưỡng này coi như không liên quan
DEFAULT_TOP_K = 5            # số fact liên quan nhất lấy ra mỗi lần

logger = logging.getLogger(__name__)

_embedder = None  # lazy-load, dùng chung 1 model cho cả tiến trình


def _get_embedder():
    global _embedder
    if _embedder is None:
        from sentence_transformers import SentenceTransformer
        _embedder = SentenceTransformer(EMBEDDING_MODEL_NAME)
    return _embedder


def _embed(text: str):
    model = _get_embedder()
    vector = model.encode(text, normalize_embeddings=True)
    return vector.tolist()


def _cosine_sim(a, b):
    a = np.array(a)
    b = np.array(b)
    denom = (np.linalg.norm(a) * np.linalg.norm(b))
    if denom == 0:
        return 0.0
    return float(np.dot(a, b) / denom)


class MemoryManager:
    def __init__(self, memory_dir, summarizer_provider):
        self.memory_dir = memory_dir
        self.history_file = os.path.join(memory_dir, "history.json")
        self.summary_file = os.path.join(memory_dir, "summary.json")
        self.facts_file = os.path.join(memory_dir, "facts.json")
        self.summarizer = summarizer_provider

        self.history = self._load(self.history_file, [])
        self.summary = self._load(self.summary_file, {"text": ""})
        self.facts = self._load_facts()

    # ==========================================================
    # Loading / migration
    # ==========================================================

    def _load(self, path, default):
        os.makedirs(self.memory_dir, exist_ok=True)
        if os.path.exists(path):
            try:
                with open(path, "r", encoding="utf-8") as f:
                    return json.load(f)
            except (json.JSONDecodeError, OSError):
                return default
        return default

    def _load_facts(self):
        """
        facts.json giờ lưu list các dict: {"text": "...", "embedding": [...]}
        Nếu file cũ còn ở dạng list[str] (bản trước khi có semantic search),
        tự động migrate sang format mới và tính embedding cho từng fact.
        """
        raw = self._load(self.facts_file, [])

        if raw and isinstance(raw[0], str):
            migrated = [
                {"text": text, "embedding": _embed(text)}
                for text in raw
            ]
            self._save(self.facts_file, migrated)
            return migrated

        return raw

    def _save(self, path, data):
        os.makedirs(self.memory_dir, exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)

    # ==========================================================
    # Conversation history
    # ==========================================================

    def add_message(self, role, content):
        self.history.append({"role": role, "content": content})
        if len(self.history) > SUMMARY_TRIGGER:
            self._summarize_old()
        self._save(self.history_file, self.history)

    def _summarize_old(self):
        if self.summarizer is None:
            return

        to_summarize = self.history[:-KEEP_RAW_AFTER_SUMMARY]
        keep = self.history[-KEEP_RAW_AFTER_SUMMARY:]
        if not to_summarize:
            return
        convo_text = "\n".join(f"{m['role']}: {m['content']}" for m in to_summarize)
        prompt = (
            "Tóm tắt đoạn hội thoại sau thành 1 đoạn văn ngắn gọn, giữ lại thông tin/ngữ cảnh quan trọng "
            "để tiếp tục trò chuyện sau này. Gộp cả tóm tắt cũ (nếu có) vào bản tóm tắt mới:\n\n"
            f"Tóm tắt cũ: {self.summary.get('text', '')}\n\n"
            f"Hội thoại mới cần gộp thêm:\n{convo_text}"
        )
        try:
            result = self.summarizer.generate(
                [{"role": "user", "content": prompt}]
            )
            summary_text = result.content.strip() if result.success else ""
            if not summary_text:
                logger.warning("Conversation summary failed; retaining full history")
                return

            new_summary = {"text": summary_text}
            self._save(self.summary_file, new_summary)
            self.summary = new_summary
            self.history = keep
        except Exception:
            logger.exception("Conversation summary failed; retaining full history")

    def get_recent_messages(self, n=8):
        return self.history[-n:]

    # ==========================================================
    # Facts (long-term memory) — với semantic search
    # ==========================================================

    def add_fact(self, fact: str):
        fact = fact.strip()
        if not fact:
            return
        if any(f["text"] == fact for f in self.facts):
            return
        self.facts.append({"text": fact, "embedding": _embed(fact)})
        self._save(self.facts_file, self.facts)

    def add_or_replace_fact(self, new_fact, old_fact=None):
        if old_fact:
            self.facts = [f for f in self.facts if f["text"] != old_fact]

        new_fact = (new_fact or "").strip()
        if new_fact and not any(f["text"] == new_fact for f in self.facts):
            self.facts.append({"text": new_fact, "embedding": _embed(new_fact)})

        self._save(self.facts_file, self.facts)

    def remove_fact_matching(self, user_text: str):
        """
        Tìm fact liên quan nhất về mặt ngữ nghĩa với câu người dùng vừa gõ,
        thay vì so khớp từ đơn giản như trước (dễ nhầm khi các fact chia sẻ
        từ chung chung).
        """
        if not self.facts:
            return None

        query_vec = _embed(user_text)

        best_fact = None
        best_score = -1.0

        for f in self.facts:
            score = _cosine_sim(query_vec, f["embedding"])
            if score > best_score:
                best_score = score
                best_fact = f

        if best_fact and best_score >= SIMILARITY_THRESHOLD:
            self.facts = [f for f in self.facts if f is not best_fact]
            self._save(self.facts_file, self.facts)
            return best_fact["text"]

        return None

    def clear_facts(self):
        self.facts = []
        self._save(self.facts_file, self.facts)

    def get_relevant_facts(self, query: str, top_k: int = DEFAULT_TOP_K):
        """
        Trả về top_k facts liên quan nhất tới câu hỏi hiện tại (chỉ những
        fact vượt ngưỡng SIMILARITY_THRESHOLD), thay vì luôn nhồi toàn bộ
        facts vào prompt.
        """
        if not self.facts:
            return []

        query_vec = _embed(query)

        scored = [
            (f["text"], _cosine_sim(query_vec, f["embedding"]))
            for f in self.facts
        ]

        scored = [item for item in scored if item[1] >= SIMILARITY_THRESHOLD]
        scored.sort(key=lambda x: x[1], reverse=True)

        return [text for text, _score in scored[:top_k]]

    # ==========================================================
    # Prompt context
    # ==========================================================

    def get_context_block(self, query: str = None):
        block = ""

        if self.summary.get("text"):
            block += f"\n\nTóm tắt các đoạn hội thoại trước đó:\n{self.summary['text']}"

        if query:
            relevant = self.get_relevant_facts(query)
        else:
            relevant = [f["text"] for f in self.facts]

        if relevant:
            block += "\n\nThông tin đã ghi nhớ về người dùng:\n" + "\n".join(
                f"- {text}" for text in relevant
            )

        return block