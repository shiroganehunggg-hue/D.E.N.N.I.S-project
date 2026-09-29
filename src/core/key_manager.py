import json
from pathlib import Path
from typing import List, Optional


class KeyManager:
    """Simple in-memory API key manager with round-robin support."""

    def __init__(self, keys: Optional[List[str]] = None) -> None:
        self._keys: List[str] = list(keys or [])
        self._current_index = 0

    @classmethod
    def from_json(cls, file_path: str) -> "KeyManager":
        path = Path(file_path)

        if not path.exists():
            return cls()

        with path.open("r", encoding="utf-8") as handle:
            payload = json.load(handle)

        if isinstance(payload, dict):
            keys = payload.get("keys", [])
        elif isinstance(payload, list):
            keys = payload
        else:
            keys = []

        return cls([str(key) for key in keys if str(key).strip()])

    def current_key(self) -> Optional[str]:
        if not self._keys:
            return None
        return self._keys[self._current_index]

    def next_key(self) -> Optional[str]:
        if not self._keys:
            return None

        self._current_index = (self._current_index + 1) % len(self._keys)
        return self.current_key()

    def reset(self) -> None:
        self._current_index = 0

    def total_count(self) -> int:
        return len(self._keys)
