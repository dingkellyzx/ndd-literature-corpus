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


def _plural_tolerant(word: str) -> str:
    if len(word) > 1 and word.endswith("y") and word[-2] not in "aeiou":
        return rf"{re.escape(word[:-1])}(?:y|ies)"
    return rf"{re.escape(word)}(?:e?s)?"


def _compile(phrase: str) -> re.Pattern[str]:
    *leading, last = phrase.split()
    parts = [re.escape(part) for part in leading] + [_plural_tolerant(last)]
    return re.compile(rf"(?<!\w){r'\s+'.join(parts)}(?!\w)", flags=re.IGNORECASE)


_POSITIVE_PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = tuple(
    (f"{group}:{phrase}", _compile(phrase))
    for group, phrases in _POSITIVE_GROUPS
    for phrase in phrases
)
_NEGATIVE_PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = tuple(
    (phrase, _compile(phrase)) for phrase in _NEGATIVE_TERMS
)


def detect_relevance_signals(title: str, abstract: str) -> RelevanceSignals:
    """Detect configured evidence phrases without making a relevance decision.

    The final word of each phrase also matches its regular plural form.
    """
    text = "\n".join(part for part in (title, abstract) if part)
    positive = [label for label, pattern in _POSITIVE_PATTERNS if pattern.search(text)]
    negative = [label for label, pattern in _NEGATIVE_PATTERNS if pattern.search(text)]
    return RelevanceSignals(positive_signals=positive, negative_signals=negative)
