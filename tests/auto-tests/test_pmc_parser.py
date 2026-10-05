from __future__ import annotations

from ndd_corpus.pmc.parser import parse_jats

JATS = b"""<?xml version="1.0"?>
<article article-type="research-article" xmlns:xlink="http://www.w3.org/1999/xlink">
  <front><article-meta>
    <article-id pub-id-type="pmc">PMC10</article-id>
    <article-id pub-id-type="pmid">123</article-id>
    <article-id pub-id-type="doi">10.1/example</article-id>
    <title-group><article-title>JATS <italic>example</italic></article-title></title-group>
    <abstract><p>Article abstract.</p></abstract>
    <permissions><license license-type="CC BY" xlink:href="https://creativecommons.org/licenses/by/4.0/"/></permissions>
  </article-meta></front>
  <body>
    <sec id="s1" sec-type="intro"><title>Introduction</title><p>Intro text.</p></sec>
    <sec id="s2"><title>Case presentation</title><p>Case text.</p></sec>
  </body>
  <back><ref-list>
    <ref id="r1"><mixed-citation>Reference one.</mixed-citation></ref>
  </ref-list></back>
</article>
"""


def test_jats_parser_extracts_article_and_normalized_sections() -> None:
    article, sections = parse_jats(JATS)

    assert article["pmcid"] == "PMC10"
    assert article["pmid"] == "123"
    assert article["doi"] == "10.1/example"
    assert article["title"] == "JATS example"
    assert article["abstract"] == "Article abstract."
    assert article["body"] == "Introduction Intro text. Case presentation Case text."
    assert article["license"] == "CC BY"
    assert article["article_type"] == "research-article"
    assert article["references"] == ["Reference one."]
    assert [section["section_type"] for section in sections] == [
        "introduction",
        "case_presentation",
    ]
