from src.core.memory_manager import MemoryManager
from src.providers.provider_result import ProviderResult


class StubSummarizer:
    def __init__(self, result):
        self.result = result

    def generate(self, messages):
        return self.result


def _memory_manager(tmp_path, result):
    manager = MemoryManager(str(tmp_path), StubSummarizer(result))
    manager.history = [
        {"role": "user", "content": f"message {index}"}
        for index in range(13)
    ]
    return manager


def test_failed_summary_retains_history(tmp_path):
    manager = _memory_manager(
        tmp_path,
        ProviderResult(success=False, error="provider unavailable"),
    )

    manager._summarize_old()

    assert len(manager.history) == 13
    assert manager.summary == {"text": ""}


def test_empty_summary_retains_history(tmp_path):
    manager = _memory_manager(tmp_path, ProviderResult(success=True, content="  "))

    manager._summarize_old()

    assert len(manager.history) == 13
    assert manager.summary == {"text": ""}


def test_successful_summary_compacts_history(tmp_path):
    manager = _memory_manager(tmp_path, ProviderResult(success=True, content="Useful summary"))

    manager._summarize_old()

    assert len(manager.history) == 6
    assert manager.summary == {"text": "Useful summary"}