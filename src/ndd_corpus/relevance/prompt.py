from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping
from typing import Any

from ndd_corpus.relevance.models import (
    ClassificationResult,
    RelevanceSignals,
    RetrievalProvenance,
)

SYSTEM_PROMPT = """Your task is NOT to decide whether the paper merely mentions a
neurodevelopmental disorder.

Your task is to determine whether this article is useful evidence for
an NDD disease/genetic/phenotypic/onset literature corpus.

HIGH:
The central topic provides NDD disease characterization, genetic evidence,
variants, genotype-phenotype evidence, patient evidence, phenotype
characterization, natural history, or onset/progression evidence.

A gene or variant is NOT required for HIGH relevance.

POSSIBLE:
The article appears genuinely NDD-focused but the title/abstract is
insufficient to determine whether useful evidence exists.

LOW:
The NDD or developmental/psychiatric diagnosis is only background for
medication adverse effects, unrelated complications, service utilization,
treatment access, policy, outreach, substance-abuse treatment, or other
non-NDD-focused research.

Do not infer evidence not present in the supplied metadata.

When uncertain because information is insufficient, prefer POSSIBLE over LOW.

Return only the requested JSON object. The reason must be one short,
evidence-based sentence. Do not include chain-of-thought."""

_USER_PROMPT_PREFIX = """Classify the supplied article metadata.
The JSON response must match this schema:
{schema}

Article metadata and evidence features:
{payload}"""


def _string_list(value: object) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        return [value] if value else []
    if isinstance(value, (list, tuple, set)):
        return [str(item) for item in value if item is not None and str(item)]
    return [str(value)]


def article_prompt_payload(
    article: Mapping[str, object],
    provenance: RetrievalProvenance,
    signals: RelevanceSignals,
) -> dict[str, object]:
    """Build the complete metadata payload while excluding full article text."""
    article_metadata = {
        "title": str(article.get("title") or ""),
        "abstract": str(article.get("abstract") or ""),
        "publication_types": _string_list(article.get("publication_types")),
        "mesh_terms": _string_list(article.get("mesh_terms")),
        "keywords": _string_list(article.get("keywords")),
    }
    return {
        "article": article_metadata,
        "retrieval_provenance": provenance.model_dump(),
        "deterministic_signals": signals.model_dump(),
    }


def _canonical_json(value: object) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _response_schema() -> dict[str, Any]:
    return ClassificationResult.model_json_schema()


def prompt_sha256() -> str:
    """Hash all static prompt text and the actual response schema."""
    prompt_material = {
        "system": SYSTEM_PROMPT,
        "user_template": _USER_PROMPT_PREFIX,
        "response_schema": _response_schema(),
    }
    return hashlib.sha256(_canonical_json(prompt_material).encode("utf-8")).hexdigest()


def compute_request_hash(
    payload: Mapping[str, object],
    *,
    model: str,
    temperature: float,
    prompt_version: str,
    actual_prompt_sha256: str,
) -> str:
    material = {
        "payload": payload,
        "model": model,
        "temperature": temperature,
        "prompt_version": prompt_version,
        "prompt_sha256": actual_prompt_sha256,
    }
    return hashlib.sha256(_canonical_json(material).encode("utf-8")).hexdigest()


def build_chat_request(
    payload: Mapping[str, object], *, model: str, temperature: float
) -> dict[str, object]:
    schema = _response_schema()
    user_prompt = _USER_PROMPT_PREFIX.format(
        schema=json.dumps(schema, ensure_ascii=False, sort_keys=True),
        payload=json.dumps(payload, ensure_ascii=False, sort_keys=True),
    )
    return {
        "model": model,
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": user_prompt},
        ],
        "temperature": temperature,
        "stream": False,
        "response_format": {
            "type": "json_schema",
            "json_schema": {
                "name": "article_relevance",
                "strict": True,
                "schema": schema,
            },
        },
    }
