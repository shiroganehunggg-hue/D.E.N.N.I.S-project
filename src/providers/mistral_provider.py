from src.config.settings import Settings
from src.providers.openai_compatible import OpenAICompatibleProvider


class MistralProvider(OpenAICompatibleProvider):

    keys_file = "src/config/mistral_keys.json"

    api_key_env = "MISTRAL_API_KEY"

    base_url = "https://api.mistral.ai/v1"

    model = "mistral-large-latest"