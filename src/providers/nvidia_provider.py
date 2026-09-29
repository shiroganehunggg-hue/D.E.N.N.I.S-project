from src.config.settings import Settings
from src.providers.openai_compatible import OpenAICompatibleProvider


class NvidiaProvider(OpenAICompatibleProvider):

    api_key_env = "NVIDIA_API_KEY"

    base_url = "https://integrate.api.nvidia.com/v1"

    model = Settings.NVIDIA_MODEL
        