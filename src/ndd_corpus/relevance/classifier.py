from __future__ import annotations

from collections.abc import Mapping
from types import TracebackType

import httpx
from pydantic import ValidationError

from ndd_corpus.config import RelevanceConfig
from ndd_corpus.relevance.models import (
    ClassificationResult,
    RelevanceSignals,
    RetrievalProvenance,
)
from ndd_corpus.relevance.prompt import article_prompt_payload, build_chat_request


class RelevanceClassifierError(RuntimeError):
    """Raised when no valid classifier response is available after retries."""


class OllamaRelevanceClassifier:
    def __init__(
        self,
        config: RelevanceConfig,
        *,
        client: httpx.Client | None = None,
    ) -> None:
        self.config = config
        self._client = client or httpx.Client(timeout=config.timeout_seconds)
        self._owns_client = client is None

    def close(self) -> None:
        if self._owns_client:
            self._client.close()

    def __enter__(self) -> OllamaRelevanceClassifier:
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_value: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        self.close()

    def classify(
        self,
        article: Mapping[str, object],
        provenance: RetrievalProvenance,
        signals: RelevanceSignals,
    ) -> ClassificationResult:
        payload = article_prompt_payload(article, provenance, signals)
        request_body = build_chat_request(
            payload,
            model=self.config.model,
            temperature=self.config.temperature,
            think=self.config.think,
        )
        attempts = self.config.max_retries + 1
        last_error: Exception | None = None
        for _attempt in range(attempts):
            try:
                response = self._client.post(
                    f"{self.config.base_url.rstrip('/')}/chat/completions",
                    json=request_body,
                )
                response.raise_for_status()
                content = response.json()["choices"][0]["message"]["content"]
                if not isinstance(content, str):
                    raise TypeError("classifier response content must be a JSON string")
                return ClassificationResult.model_validate_json(content)
            except (
                httpx.HTTPError,
                KeyError,
                IndexError,
                TypeError,
                ValueError,
                ValidationError,
            ) as error:
                last_error = error
        raise RelevanceClassifierError(
            f"Relevance classifier failed after {attempts} attempts: {last_error}"
        ) from last_error
