from __future__ import annotations

from typing import Any

from lxml import etree


def _text(element: etree._Element | None) -> str | None:
    if element is None:
        return None
    value = " ".join(" ".join(element.itertext()).split())
    return value or None


def _first(root: etree._Element, expression: str) -> etree._Element | None:
    matches = root.xpath(expression)
    return matches[0] if matches else None


def _identifier(root: etree._Element, identifier_type: str) -> str | None:
    return _text(
        _first(
            root,
            f"//*[local-name()='article-id'][@pub-id-type='{identifier_type}']",
        )
    )


def _section_type(title: str | None, sec_type: str | None) -> str:
    value = f"{sec_type or ''} {title or ''}".casefold()
    rules = [
        ("intro", "introduction"),
        ("method", "methods"),
        ("result", "results"),
        ("discussion", "discussion"),
        ("case presentation", "case_presentation"),
        ("case report", "case_report"),
        ("conclu", "conclusion"),
    ]
    return next((normalized for token, normalized in rules if token in value), "other")


def parse_jats(content: bytes) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    root = etree.fromstring(
        content,
        parser=etree.XMLParser(resolve_entities=False, no_network=True, recover=False),
    )
    title = _text(_first(root, "//*[local-name()='article-title']"))
    abstract = _text(_first(root, "//*[local-name()='abstract']"))
    body_element = _first(root, "//*[local-name()='body']")
    body = _text(body_element)
    sections = []
    if body_element is not None:
        for index, section in enumerate(body_element.xpath(".//*[local-name()='sec']")):
            section_title = _text(_first(section, "./*[local-name()='title']"))
            paragraphs = [
                value
                for paragraph in section.xpath("./*[local-name()='p']")
                if (value := _text(paragraph))
            ]
            sections.append(
                {
                    "pmcid": _identifier(root, "pmc"),
                    "section_index": index,
                    "section_id": section.get("id"),
                    "section_title": section_title,
                    "section_type": _section_type(section_title, section.get("sec-type")),
                    "text": "\n\n".join(paragraphs),
                }
            )
    license_element = _first(root, "//*[local-name()='license']")
    references = [
        value
        for reference in root.xpath("//*[local-name()='ref']")
        if (value := _text(reference))
    ]
    article = {
        "pmcid": _identifier(root, "pmc"),
        "pmid": _identifier(root, "pmid"),
        "doi": _identifier(root, "doi"),
        "title": title,
        "abstract": abstract,
        "body": body,
        "sections": sections,
        "references": references,
        "license": license_element.get("license-type") if license_element is not None else None,
        "article_type": root.get("article-type"),
    }
    return article, sections
