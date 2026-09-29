from src.config.settings import Settings
from src.providers.openai_compatible import OpenAICompatibleProvider


class CohereProvider(OpenAICompatibleProvider):

    api_key_env = "COHERE_API_KEY"

    base_url = "https://api.cohere.ai/compatibility/v1"

    model = "command-a-plus-05-2026"