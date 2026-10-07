from __future__ import annotations

import copy
import json
from typing import Any

import httpx
import pytest
import respx

from ndd_corpus.config import RelevanceConfig
from ndd_corpus.relevance.classifier import (
    OllamaRelevanceClassifier,
    RelevanceClassifierError,
)
from ndd_corpus.relevance.models import RelevanceSignals, RetrievalProvenance
from ndd_corpus.relevance.prompt import (
    SYSTEM_PROMPT,
    article_prompt_payload,
    build_chat_request,
    compute_request_hash,
    prompt_sha256,
)


def _article() -> dict[str, object]:
    return {
        "title": "SETD1B-associated neurodevelopmental disorder",
        "abstract": "De novo variants occurred with developmental delay and seizures.",
        "publication_types": ["Journal Article"],
        "mesh_terms": ["Intellectual Disability"],
        "keywords": ["SETD1B"],
        "pmc_full_text": "This content must never be sent.",
    }


def _provenance() -> RetrievalProvenance:
    return RetrievalProvenance(
        retrieval_branches=["disease_name", "generic_ndd"],
        mondo_ids=["MONDO:0000001"],
        matched_search_terms=["SETD1B disorder"],
        query_ids=["query-1", "query-2"],
    )


def _signals() -> RelevanceSignals:
    return RelevanceSignals(
        positive_signals=["genetic:de novo", "phenotype:developmental delay"],
        negative_signals=[],
    )


def _response(label: str = "HIGH") -> dict[str, object]:
    return {
        "choices": [
            {
                "message": {
                    "content": json.dumps(
                        {
                            "relevance_label": label,
                            "evidence_types": ["disease_focus", "genetic", "phenotype"],
                            "reason": "Reports genetic and phenotypic NDD evidence.",
                        }
                    )
                }
            }
        ]
    }


def test_prompt_contains_required_recall_protecting_instructions() -> None:
    assert "A gene or variant is NOT required for HIGH relevance." in SYSTEM_PROMPT
    assert "prefer POSSIBLE over LOW" in SYSTEM_PROMPT
    assert "Do not infer evidence not present" in SYSTEM_PROMPT
    assert len(prompt_sha256()) == 64


def test_prompt_payload_uses_only_allowed_article_metadata() -> None:
    payload = article_prompt_payload(_article(), _provenance(), _signals())

    assert payload["article"] == {
        "title": "SETD1B-associated neurodevelopmental disorder",
        "abstract": "De novo variants occurred with developmental delay and seizures.",
        "publication_types": ["Journal Article"],
        "mesh_terms": ["Intellectual Disability"],
        "keywords": ["SETD1B"],
    }
    assert "pmc_full_text" not in json.dumps(payload)
    assert payload["retrieval_provenance"] == _provenance().model_dump()
    assert payload["deterministic_signals"] == _signals().model_dump()


def test_chat_request_uses_openai_compatible_structured_output() -> None:
    payload = article_prompt_payload(_article(), _provenance(), _signals())
    request = build_chat_request(
        payload, model="qwen3:14b", temperature=0.0, think=False
    )

    assert request["model"] == "qwen3:14b"
    assert request["temperature"] == 0.0
    assert request["stream"] is False
    assert request["messages"][0] == {"role": "system", "content": SYSTEM_PROMPT}
    response_format = request["response_format"]
    assert response_format["type"] == "json_schema"
    assert response_format["json_schema"]["strict"] is True
    assert response_format["json_schema"]["schema"]["additionalProperties"] is False
    assert request["reasoning_effort"] == "none"


def test_chat_request_leaves_model_default_reasoning_when_thinking_enabled() -> None:
    payload = article_prompt_payload(_article(), _provenance(), _signals())
    request = build_chat_request(payload, model="qwen3:14b", temperature=0.0, think=True)

    assert "reasoning_effort" not in request


@pytest.mark.parametrize(
    ("mutation", "value"),
    [
        (("article", "title"), "Different title"),
        (("article", "abstract"), "Different abstract"),
        (("article", "mesh_terms"), ["Epilepsy"]),
        (("article", "keywords"), ["rare"]),
        (("article", "publication_types"), ["Case Reports"]),
        (("retrieval_provenance", "query_ids"), ["query-9"]),
        (("deterministic_signals", "negative_signals"), ["outreach"]),
    ],
)
def test_request_hash_changes_with_every_article_input(
    mutation: tuple[str, str], value: object
) -> None:
    payload = article_prompt_payload(_article(), _provenance(), _signals())
    changed = copy.deepcopy(payload)
    changed[mutation[0]][mutation[1]] = value  # type: ignore[index]
    common = {
        "model": "qwen3:14b",
        "temperature": 0.0,
        "prompt_version": "1",
        "actual_prompt_sha256": "a" * 64,
        "think": False,
    }

    assert compute_request_hash(payload, **common) != compute_request_hash(changed, **common)


@pytest.mark.parametrize(
    ("changed_setting", "value"),
    [
        ("model", "another-model"),
        ("temperature", 0.2),
        ("prompt_version", "2"),
        ("actual_prompt_sha256", "b" * 64),
        ("think", True),
    ],
)
def test_request_hash_changes_with_classifier_settings(
    changed_setting: str, value: object
) -> None:
    payload = article_prompt_payload(_article(), _provenance(), _signals())
    settings: dict[str, Any] = {
        "model": "qwen3:14b",
        "temperature": 0.0,
        "prompt_version": "1",
        "actual_prompt_sha256": "a" * 64,
        "think": False,
    }
    original = compute_request_hash(payload, **settings)
    settings[changed_setting] = value

    assert compute_request_hash(payload, **settings) != original


@pytest.mark.parametrize("label", ["HIGH", "POSSIBLE", "LOW"])
@respx.mock
def test_classifier_posts_to_ollama_and_validates_each_label(label: str) -> None:
    route = respx.post("http://127.0.0.1:11434/v1/chat/completions").mock(
        return_value=httpx.Response(200, json=_response(label))
    )
    classifier = OllamaRelevanceClassifier(RelevanceConfig(max_retries=0))

    result = classifier.classify(_article(), _provenance(), _signals())

    assert result.relevance_label == label
    assert result.evidence_types == ["disease_focus", "genetic", "phenotype"]
    assert route.call_count == 1
    sent = json.loads(route.calls[0].request.content)
    assert sent["response_format"]["type"] == "json_schema"
    assert sent["reasoning_effort"] == "none"
    assert "pmc_full_text" not in json.dumps(sent)


@respx.mock
def test_classifier_retries_malformed_json_then_succeeds() -> None:
    route = respx.post("http://127.0.0.1:11434/v1/chat/completions").mock(
        side_effect=[
            httpx.Response(200, json={"choices": [{"message": {"content": "not-json"}}]}),
            httpx.Response(200, json=_response("POSSIBLE")),
        ]
    )
    classifier = OllamaRelevanceClassifier(RelevanceConfig(max_retries=1))

    result = classifier.classify(_article(), _provenance(), _signals())

    assert result.relevance_label == "POSSIBLE"
    assert route.call_count == 2


@respx.mock
def test_classifier_raises_after_all_retries_are_exhausted() -> None:
    route = respx.post("http://127.0.0.1:11434/v1/chat/completions").mock(
        return_value=httpx.Response(503, text="unavailable")
    )
    classifier = OllamaRelevanceClassifier(RelevanceConfig(max_retries=2))

    with pytest.raises(RelevanceClassifierError, match="after 3 attempts"):
        classifier.classify(_article(), _provenance(), _signals())

    assert route.call_count == 3


@respx.mock
def test_classifier_rejects_unknown_evidence_type() -> None:
    invalid = _response()
    content = json.loads(invalid["choices"][0]["message"]["content"])  # type: ignore[index]
    content["evidence_types"] = ["invented"]
    invalid["choices"][0]["message"]["content"] = json.dumps(content)  # type: ignore[index]
    respx.post("http://127.0.0.1:11434/v1/chat/completions").mock(
        return_value=httpx.Response(200, json=invalid)
    )
    classifier = OllamaRelevanceClassifier(RelevanceConfig(max_retries=0))

    with pytest.raises(RelevanceClassifierError):
        classifier.classify(_article(), _provenance(), _signals())
