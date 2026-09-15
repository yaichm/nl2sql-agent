"""Model provider interface."""

from dataclasses import dataclass
from typing import Protocol


@dataclass
class Completion:
    text: str
    prompt_tokens: int
    completion_tokens: int
    latency_s: float
    model: str

    @property
    def total_tokens(self) -> int:
        return self.prompt_tokens + self.completion_tokens


class LLMProvider(Protocol):
    """Everything the rest of the project needs from a model."""

    name: str
    model: str

    def complete(self, system: str, user: str, temperature: float = 0.0) -> Completion: ...
