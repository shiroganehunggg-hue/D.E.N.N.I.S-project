from dataclasses import dataclass, field
from typing import List, Dict, Any


@dataclass
class ProviderResult:

    success: bool

    content: str = ""

    tool_calls: List[Dict[str, Any]] = field(default_factory=list)

    error: str = ""

    provider: str = ""

    latency: float = 0.0

    reasoning: str = ""