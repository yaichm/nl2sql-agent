"""Fournisseur pour toute API au format OpenAI.

Mistral et Ollama exposent la même route /v1/chat/completions avec le même
schéma. Une seule implémentation suffit donc, paramétrée par l'URL et la clé.
"""

import time
from typing import Any

import httpx

from nl2sql_agent.providers.base import Completion


class OpenAICompatibleProvider:
    def __init__(
        self,
        name: str,
        base_url: str,
        model: str,
        api_key: str = "",
        timeout: float = 120.0,
    ) -> None:
        self.name = name
        self.model = model
        self._url = f"{base_url.rstrip('/')}/chat/completions"
        self._headers = {"Authorization": f"Bearer {api_key}"} if api_key else {}
        self._timeout = timeout

    def complete(self, system: str, user: str, temperature: float = 0.0) -> Completion:
        payload: dict[str, Any] = {
            "model": self.model,
            "temperature": temperature,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
        }

        started = time.perf_counter()
        response = httpx.post(self._url, headers=self._headers, json=payload, timeout=self._timeout)
        latency = time.perf_counter() - started

        if response.status_code != 200:
            raise RuntimeError(
                f"{self.name} a répondu {response.status_code} : {response.text[:300]}"
            )

        data = response.json()
        usage = data.get("usage") or {}

        return Completion(
            text=data["choices"][0]["message"]["content"],
            prompt_tokens=usage.get("prompt_tokens", 0),
            completion_tokens=usage.get("completion_tokens", 0),
            latency_s=latency,
            model=self.model,
        )
