from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from typing import Any

from ndd_corpus.corpus.deduplicate import deduplicate_records, normalize_doi


@dataclass(frozen=True, slots=True)
class CorpusResult:
    articles: list[dict[str, Any]]
    sections: list[dict[str, Any]]
    disease_retrieval: list[dict[str, Any]]
    deduplication_log: list[dict[str, Any]]


def _truthy(value: object) -> bool:
    return value is True or str(value).casefold() in {"1", "true", "yes"}


def _article_id(pmid: str | None, pmcid: str | None, doi: str | None, index: int) -> str:
    if pmid:
        return f"PMID:{pmid}"
    if pmcid:
        return f"PMCID:{pmcid}"
    if doi:
        return f"DOI:{normalize_doi(doi)}"
    return f"LOCAL:{index:08d}"


def merge_corpus(
    pubmed_rows: list[dict[str, Any]],
    pmc_rows: list[dict[str, Any]],
    retrieval_rows: list[dict[str, Any]],
    section_rows: list[dict[str, Any]],
) -> CorpusResult:
    tagged = [dict(row, _source="pubmed") for row in pubmed_rows]
    tagged.extend(dict(row, _source="pmc") for row in pmc_rows)
    groups, decisions = deduplicate_records(tagged)
    retrieval_by_pmid: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in retrieval_rows:
        retrieval_by_pmid[str(row["pmid"])].append(row)
    articles = []
    pmcid_to_article: dict[str, str] = {}
    disease_retrieval = []
    for index, group in enumerate(groups):
        pubmed = next((row for row in group if row["_source"] == "pubmed"), {})
        pmc = next((row for row in group if row["_source"] == "pmc"), {})
        pmid_value = pubmed.get("pmid") or pmc.get("pmid")
        pmcid_value = pmc.get("pmcid") or pubmed.get("pmcid_if_present")
        doi_value = pubmed.get("doi") or pmc.get("doi")
        pmid = str(pmid_value) if pmid_value else None
        pmcid = str(pmcid_value) if pmcid_value else None
        doi = str(doi_value) if doi_value else None
        article_id = _article_id(pmid, pmcid, doi, index)
        provenance = retrieval_by_pmid.get(pmid or "", [])
        mondo_ids = sorted({str(row["mondo_id"]) for row in provenance if row.get("mondo_id")})
        branches = sorted({str(row["retrieval_branch"]) for row in provenance})
        queries = sorted({str(row["query"]) for row in provenance})
        abstract_pubmed = pubmed.get("abstract")
        abstract_pmc = pmc.get("abstract")
        article = {
            "article_id": article_id,
            "pmid": pmid,
            "pmcid": pmcid,
            "doi": doi,
            "title": pubmed.get("title") or pmc.get("title"),
            "abstract": abstract_pubmed or abstract_pmc,
            "abstract_pubmed": abstract_pubmed,
            "abstract_pmc": abstract_pmc,
            "publication_year": pubmed.get("publication_year"),
            "journal": pubmed.get("journal"),
            "has_abstract": bool(abstract_pubmed or abstract_pmc),
            "has_fulltext": bool(pmc),
            "mondo_ids": mondo_ids,
            "retrieval_branches": branches,
            "retrieval_queries": queries,
            "mesh_terms": pubmed.get("mesh_terms", []),
            "keywords": pubmed.get("keywords", []),
            "publication_types": pubmed.get("publication_types", []),
            "pmc_version": pmc.get("pmc_version"),
            "pmc_license": pmc.get("pmc_license") or pmc.get("license"),
            "is_manuscript": _truthy(pmc.get("is_manuscript")) if pmc else False,
            "is_retracted": _truthy(pubmed.get("is_retracted"))
            or _truthy(pmc.get("is_retracted")),
            "pubmed_raw_file": pubmed.get("pubmed_raw_file"),
            "pmc_xml_file": pmc.get("pmc_xml_file"),
        }
        articles.append(article)
        if pmcid:
            pmcid_to_article[pmcid] = article_id
        for row in provenance:
            disease_retrieval.append(
                {
                    "pmid": pmid,
                    "mondo_id": row.get("mondo_id"),
                    "retrieval_branch": row.get("retrieval_branch"),
                    "matched_search_term": row.get("matched_search_term"),
                    "query_id": row.get("query_id"),
                }
            )
    sections = []
    for row in section_rows:
        pmcid = str(row.get("pmcid") or "")
        if pmcid not in pmcid_to_article:
            continue
        section = dict(row)
        section["article_id"] = pmcid_to_article[pmcid]
        sections.append(section)
    unique_retrieval = {
        (
            row["pmid"],
            row["mondo_id"],
            row["retrieval_branch"],
            row["matched_search_term"],
            row["query_id"],
        ): row
        for row in disease_retrieval
    }
    return CorpusResult(
        articles=sorted(articles, key=lambda row: str(row["article_id"])),
        sections=sorted(
            sections,
            key=lambda row: (str(row["article_id"]), int(row.get("section_index", 0))),
        ),
        disease_retrieval=list(unique_retrieval.values()),
        deduplication_log=decisions,
    )

