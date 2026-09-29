class Settings:
    HISTORY_LIMIT = 6
    PROVIDER_RETRY_COUNT = 2
    PROVIDER_RETRY_DELAY = 0.8
    PROVIDER_TIMEOUT_SECONDS = 20
    PROVIDER_MAX_ATTEMPTS = 3
    GEMINI_MODEL = "gemini-flash-latest"
    GROQ_MODEL = "llama-3.3-70b-versatile"
    MISTRAL_MODEL = "mistral-large-latest"
    NVIDIA_MODEL = "meta/llama-3.3-70b-instruct"
    COHERE_MODEL = "command-r-plus"
    HUGGINGFACE_MODEL = "openai/gpt-oss-120b"
    OPENROUTER_MODEL = "openrouter/free"
    # Optional runtime flags
    DEBUG = False
    ALLOW_UNSAFE_PYTHON_TOOL = False

    # Project root used by file tools when not explicitly configured.
    # Defaults to the repository root.
    from pathlib import Path
    PROJECT_ROOT = str(Path(__file__).resolve().parents[2])
