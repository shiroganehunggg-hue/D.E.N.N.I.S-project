from src.core.metrics import ProviderMetrics


def test_success_metrics_are_persisted_and_loaded(tmp_path):
    metrics_path = tmp_path / "provider_metrics.json"
    metrics = ProviderMetrics(str(metrics_path))

    metrics.record_success("Mistral", 0.4)

    restored = ProviderMetrics(str(metrics_path))
    restored.load()

    stats = restored.get("Mistral")
    assert stats["total_requests"] == 1
    assert stats["successful_requests"] == 1
    assert stats["average_latency"] == 0.4