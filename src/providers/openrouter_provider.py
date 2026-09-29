from src.config.settings import Settings
from src.providers.openai_compatible import OpenAICompatibleProvider


class OpenRouterProvider(OpenAICompatibleProvider):

    api_key_env = "OPENROUTER_API_KEY"

    base_url = "https://openrouter.ai/api/v1"

    model = "openrouter/free"