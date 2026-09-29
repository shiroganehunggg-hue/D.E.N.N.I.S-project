from src.providers.openai_compatible import OpenAICompatibleProvider


class HuggingFaceProvider(OpenAICompatibleProvider):

    keys_file = "src/config/hf_keys.json"

    # Fallback nếu không có file JSON
    api_key_env = "HF_API_KEY"

    base_url = "https://router.huggingface.co/v1"

    model = "openai/gpt-oss-120b"

    extra_params = {"reasoning_effort": "medium"}

    is_reasoning_model = True