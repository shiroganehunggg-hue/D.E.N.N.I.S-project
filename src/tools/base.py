from abc import ABC, abstractmethod
from typing import Any, Dict


class Tool(ABC):
    """Interface chuẩn cho mọi tool mà DENNIS có thể gọi."""

    enabled = True
    name: str
    description: str

    @abstractmethod
    def run(self, **kwargs) -> str:
        """Thực thi tool, trả về kết quả dạng string để đưa lại cho LLM."""
        ...

    @abstractmethod
    def schema(self) -> Dict[str, Any]:
        """Trả về JSON schema mô tả tham số, dùng để LLM biết cách gọi."""
        ...