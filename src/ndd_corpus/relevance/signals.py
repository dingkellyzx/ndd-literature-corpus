from __future__ import annotations

import re

from ndd_corpus.relevance.models import RelevanceSignals

_POSITIVE_GROUPS: tuple[tuple[str, tuple[str, ...]], ...] = (
    (
        "genetic",
        (
            "gene",
            "genetic",
            "mutation",
            "variant",
            "pathogenic",
            "likely pathogenic",
            "de novo",
            "heterozygous",
            "homozygous",
            "biallelic",
            "compound heterozygous",
            "exome",
            "genome",
            "sequencing",
            "genotype",
        ),
    ),
    (
        "phenotype",
        (
            "phenotype",
            "phenotypic",
            "clinical features",
            "developmental delay",
            "intellectual disability",
            "seizure",
            "epilepsy",
            "speech delay",
            "language delay",
            "motor delay",
        ),
    ),
    (
        "patient",
        (
            "patient",
            "patients",
            "proband",
            "case report",
            "case series",
            "family",
            "families",
            "cohort",
        ),
    ),
    (
        "temporal",
        (
            "onset",
            "age at onset",
            "natural history",
            "longitudinal",
            "progression",
            "progressive",
            "follow-up",
        ),
    ),
)

_NEGATIVE_TERMS: tuple[str, ...] = (
    "service utilization",
    "treatment access",
    "health policy",
    "outreach",
    "medication safety",
    "adverse effect",
    "drug toxicity",
    "screening program",
    "behavioral intervention",
    "substance abuse treatment",
)


def _matches(text: str, phrase: str) -> bool:
    parts = [re.escape(part) for part in phrase.split()]
    pattern = rf"(?<!\w){r'\s+'.join(parts)}(?!\w)"
    return re.search(pattern, text, flags=re.IGNORECASE) is not None


def detect_relevance_signals(title: str, abstract: str) -> RelevanceSignals:
    """Detect configured evidence phrases without making a relevance decision."""
    text = "\n".join(part for part in (title, abstract) if part)
    positive = [
        f"{group}:{phrase}"
        for group, phrases in _POSITIVE_GROUPS
        for phrase in phrases
        if _matches(text, phrase)
    ]
    negative = [phrase for phrase in _NEGATIVE_TERMS if _matches(text, phrase)]
    return RelevanceSignals(positive_signals=positive, negative_signals=negative)
