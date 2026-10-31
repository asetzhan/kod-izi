"""Local model through Ollama (Q-08, Q-09: student data does not leave the server).

Chat: POST /api/chat with a JSON schema in `format`; embeddings: POST /api/embed.
"""

from typing import Any

import httpx

from app.llm.base import LLMRequest, LLMResponse, render_data_blocks


class LLMUnavailableError(RuntimeError):
    pass


class OllamaProvider:
    name = "ollama"

    def __init__(
        self,
        base_url: str,
        chat_model: str,
        embed_model: str,
        *,
        timeout_s: float = 300.0,
        http: httpx.Client | None = None,
    ) -> None:
        self._http = http or httpx.Client(base_url=base_url, timeout=timeout_s)
        self._chat_model = chat_model
        self._embed_model = embed_model

    def complete(self, request: LLMRequest) -> LLMResponse:
        model = request.model or self._chat_model
        body: dict[str, Any] = {
            "model": model,
            "stream": False,
            "messages": [
                {"role": "system", "content": request.system},
                {"role": "user", "content": render_data_blocks(request.data_blocks)},
            ],
            "options": {"temperature": 0, "num_predict": request.max_output_tokens},
        }
        if request.response_schema is not None:
            body["format"] = request.response_schema
        try:
            response = self._http.post("/api/chat", json=body)
            response.raise_for_status()
            data = response.json()
            text = str(data["message"]["content"])
        except (httpx.HTTPError, KeyError, ValueError) as exc:
            raise LLMUnavailableError(f"Ollama chat failed: {exc}") from exc
        return LLMResponse(
            text=text,
            model=model,
            prompt_version=request.prompt_version,
            input_tokens=int(data.get("prompt_eval_count", 0)),
            output_tokens=int(data.get("eval_count", 0)),
        )

    def embed(self, texts: list[str]) -> list[list[float]]:
        try:
            response = self._http.post(
                "/api/embed", json={"model": self._embed_model, "input": texts}
            )
            response.raise_for_status()
            vectors = response.json()["embeddings"]
        except (httpx.HTTPError, KeyError, ValueError) as exc:
            raise LLMUnavailableError(f"Ollama embed failed: {exc}") from exc
        return [[float(x) for x in v] for v in vectors]
