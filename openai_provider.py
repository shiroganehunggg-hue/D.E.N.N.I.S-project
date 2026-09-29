from .base import AIProvider

class OpenAIProvider(AIProvider):

    def generate(self, messages):
        return "Hello, I am DENNIS."
    