from src.providers.openai_compatible import OpenAICompatibleProvider


class GroqProvider(OpenAICompatibleProvider):

    keys_file = "src/config/groq_keys.json"

    base_url = "https://api.groq.com/openai/v1"

    model = "openai/gpt-oss-120b"

    extra_params = {"reasoning_effort": "medium"}

    is_reasoning_model = True   # mới: đánh dấu cho router nhận diện