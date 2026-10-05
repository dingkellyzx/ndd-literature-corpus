from __future__ import annotations

import re
from typing import Any

from lxml import etree


def _text(element: etree._Element | None) -> str | None:
    if element is None:
        return None
    value = " ".join("".join(element.itertext()).split())
    return value or None


def _year(citation: etree._Element) -> int | None:
    pubdate = citation.find("./Article/Journal/JournalIssue/PubDate")
    direct = _text(pubdate.find("Year")) if pubdate is not None else None
    if direct and direct.isdigit():
        return int(direct)
    medline = _text(pubdate.find("MedlineDate")) if pubdate is not None else None
    match = re.search(r"(?:18|19|20)\d{2}", medline or "")
    return int(match.group()) if match else None


def _authors(citation: etree._Element) -> list[str]:
    values = []
    for author in citation.findall("./Article/AuthorList/Author"):
        collective = _text(author.find("CollectiveName"))
        if collective:
            values.append(collective)
            continue
        first = _text(author.find("ForeName")) or _text(author.find("Initials"))
        last = _text(author.find("LastName"))
        name = " ".join(part for part in (first, last) if part)
        if name:
            values.append(name)
    return values


def parse_pubmed_xml(content: bytes) -> list[dict[str, Any]]:
    root = etree.fromstring(
        content,
        parser=etree.XMLParser(resolve_entities=False, no_network=True, recover=False),
    )
    records: list[dict[str, Any]] = []
    for publication in root.findall("./PubmedArticle"):
        citation = publication.find("MedlineCitation")
        if citation is None:
            continue
        pmid = _text(citation.find("PMID"))
        if not pmid:
            raise ValueError("PubMed article has no PMID")
        article_ids = {
            str(item.get("IdType", "")).casefold(): _text(item)
            for item in publication.findall("./PubmedData/ArticleIdList/ArticleId")
        }
        sections = []
        for abstract in citation.findall("./Article/Abstract/AbstractText"):
            text = _text(abstract)
            if text:
                sections.append(
                    {
                        "label": abstract.get("Label"),
                        "category": abstract.get("NlmCategory"),
                        "text": text,
                    }
                )
        abstract_text = "\n\n".join(section["text"] for section in sections) or None
        publication_types = [
            value
            for item in citation.findall("./Article/PublicationTypeList/PublicationType")
            if (value := _text(item))
        ]
        correction_types = {
            str(item.get("RefType", ""))
            for item in citation.findall("./CommentsCorrectionsList/CommentsCorrections")
        }
        records.append(
            {
                "pmid": pmid,
                "pmcid_if_present": article_ids.get("pmc"),
                "doi": article_ids.get("doi"),
                "title": _text(citation.find("./Article/ArticleTitle")),
                "abstract": abstract_text,
                "structured_abstract_sections": sections,
                "journal": _text(citation.find("./Article/Journal/Title")),
                "publication_date": _text(
                    citation.find("./Article/Journal/JournalIssue/PubDate/MedlineDate")
                ),
                "publication_year": _year(citation),
                "authors": _authors(citation),
                "keywords": [
                    value
                    for item in citation.findall("./KeywordList/Keyword")
                    if (value := _text(item))
                ],
                "mesh_terms": [
                    value
                    for item in citation.findall("./MeshHeadingList/MeshHeading/DescriptorName")
                    if (value := _text(item))
                ],
                "publication_types": publication_types,
                "language": [
                    value
                    for item in citation.findall("./Article/Language")
                    if (value := _text(item))
                ],
                "has_abstract": abstract_text is not None,
                "is_retracted": "Retracted Publication" in publication_types
                or bool(correction_types & {"RetractionIn", "RetractionOf"}),
            }
        )
    return records

