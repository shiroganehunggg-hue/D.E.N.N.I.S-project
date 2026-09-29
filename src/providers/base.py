from abc import ABC, abstractmethod
from typing import List, Dict, Any


class AIProvider(ABC):
    """
    Base class cho tất cả AI providers.

    Mọi provider (Gemini, Groq, Nvidia, OpenRouter...)
    đều phải kế thừa class này.
    """

    def __init__(self):
        # Tên provider (mặc định là tên class)
        self.name = self.__class__.__name__

        # Router sẽ dùng sau này để bỏ qua provider
        # khi hết quota hoặc đang lỗi.
        self.available = True

    @abstractmethod
    def generate(self, messages: List[Dict[str, Any]], tools: List[Dict[str, Any]] | None = None) -> str:
        """
        Sinh phản hồi từ danh sách messages.

        Parameters
        ----------
        messages : list
            Danh sách message theo format OpenAI.

        Returns
        -------
        str
            Phản hồi của AI. Nếu provider hỗ trợ tool-calling native, có thể
            trả về cấu trúc dict đại diện cho tool call thay vì text.
        """
        raise NotImplementedError

    def __str__(self):
        return self.name

    def __repr__(self):
        return self.name
