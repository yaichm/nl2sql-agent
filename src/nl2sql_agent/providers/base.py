"""Interface des fournisseurs de modèles."""

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
    """Tout ce dont le reste du projet a besoin d'un modèle."""

    name: str

    def complete(self, system: str, user: str, temperature: float = 0.0) -> Completion: ...
