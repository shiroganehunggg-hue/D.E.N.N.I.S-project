import json
import os
import time


class ProviderMetrics:

    def __init__(self, storage_path: str | None = None):
        self._stats = {}
        self._storage_path = storage_path

    def load(self) -> None:
        if not self._storage_path or not os.path.exists(self._storage_path):
            return

        try:
            with open(self._storage_path, "r", encoding="utf-8") as file:
                self._stats = json.load(file)
        except Exception as exc:
            print(f"[ProviderMetrics] Khong the tai metrics: {exc}")
            self._stats = {}

    def save(self) -> None:
        if self._storage_path is None:
            return

        try:
            directory = os.path.dirname(self._storage_path)
            if directory:
                os.makedirs(directory, exist_ok=True)

            with open(self._storage_path, "w", encoding="utf-8") as file:
                json.dump(self._stats, file, ensure_ascii=False, indent=2)
        except Exception as exc:
            print(f"[ProviderMetrics] Khong the luu metrics: {exc}")

    def _get_stats(self, provider_name: str) -> dict:
        if provider_name not in self._stats:
            self._stats[provider_name] = {
                "total_requests": 0,
                "successful_requests": 0,
                "failed_requests": 0,
                "average_latency": 0.0,
                "total_latency": 0.0,
                "last_failure_time": None,
                "last_error_type": None,
            }

        return self._stats[provider_name]

    def record_success(self, provider_name: str, latency: float):
        stats = self._get_stats(provider_name)
        stats["total_requests"] += 1
        stats["successful_requests"] += 1
        stats["total_latency"] += latency
        stats["average_latency"] = (
            stats["total_latency"] / stats["total_requests"]
        )
        self.save()

    def record_failure(
        self,
        provider_name: str,
        latency: float,
        error_message: str = "",
    ):
        stats = self._get_stats(provider_name)
        stats["total_requests"] += 1
        stats["failed_requests"] += 1
        stats["total_latency"] += latency
        stats["average_latency"] = (
            stats["total_latency"] / stats["total_requests"]
        )
        self.save()
        stats["last_failure_time"] = time.time()

        rate_limit_keywords = (
            "429",
            "rate limit",
            "rate_limit",
            "too many requests",
            "quota",
        )
        error_message = error_message.lower()
        stats["last_error_type"] = (
            "rate_limit"
            if any(keyword in error_message for keyword in rate_limit_keywords)
            else "other"
        )
        self.save()

    def is_in_cooldown(
        self,
        provider_name: str,
        cooldown_seconds: float = 60.0,
    ) -> bool:
        stats = self._get_stats(provider_name)
        last_failure_time = stats["last_failure_time"]

        return (
            stats["last_error_type"] == "rate_limit"
            and last_failure_time is not None
            and (time.time() - last_failure_time) < cooldown_seconds
        )

    def get(self, provider_name: str) -> dict:
        return dict(self._get_stats(provider_name))

    def get_all(self) -> dict:
        return {
            provider: dict(stats)
            for provider, stats in self._stats.items()
        }

    def reset(self):
        self._stats.clear()
