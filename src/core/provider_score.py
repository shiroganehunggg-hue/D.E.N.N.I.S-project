class ProviderScore:

    def __init__(self, metrics):
        self.metrics = metrics

    def _normalize_provider_name(self, provider_name: str) -> str:
        if provider_name.endswith("Provider"):
            return provider_name[:-8]
        return provider_name

    def score(self, provider_name: str) -> float:
        name = self._normalize_provider_name(provider_name)
        stats = self.metrics.get_all().get(name)

        if not stats:
            return 0.0

        total_requests = stats.get("total_requests", 0)

        if total_requests == 0:
            return 0.0

        success_rate = stats.get("successful_requests", 0) / total_requests
        confidence = min(total_requests / 5, 1.0)

        return (
            (success_rate * 100)
            - stats.get("average_latency", 0.0)
            - stats.get("failed_requests", 0) * 5
        ) * confidence
