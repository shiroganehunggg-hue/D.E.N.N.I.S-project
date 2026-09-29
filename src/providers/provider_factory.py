from src.providers.gemini_provider import GeminiProvider
from src.providers.groq_provider import GroqProvider
from src.providers.nvidia_provider import NvidiaProvider
from src.providers.mistral_provider import MistralProvider
from src.providers.cohere_provider import CohereProvider
from src.providers.huggingface_provider import HuggingFaceProvider
from src.providers.openrouter_provider import OpenRouterProvider


class ProviderFactory:
    """
    Tạo toàn bộ provider của Dennis.

    Sau này chỉ cần sửa file này nếu muốn:
        - thêm provider
        - bỏ provider
        - đổi thứ tự provider
    """

    @staticmethod
    def create_all():
        providers = [
            GeminiProvider(),
            GroqProvider(),
            NvidiaProvider(),
            MistralProvider(),
            CohereProvider(),
            HuggingFaceProvider(),
            OpenRouterProvider(),
        ]
        return [provider for provider in providers if getattr(provider, "client", None) is not None]