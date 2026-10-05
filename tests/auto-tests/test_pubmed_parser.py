from __future__ import annotations

from ndd_corpus.pubmed.fetch import plan_batches
from ndd_corpus.pubmed.parser import parse_pubmed_xml

PUBMED_XML = b"""<?xml version="1.0" encoding="UTF-8"?>
<PubmedArticleSet>
  <PubmedArticle>
    <MedlineCitation Status="MEDLINE">
      <PMID Version="1">123</PMID>
      <Article>
        <ArticleTitle>Example <i>structured</i> article</ArticleTitle>
        <Abstract>
          <AbstractText Label="BACKGROUND" NlmCategory="BACKGROUND">First section.</AbstractText>
          <AbstractText Label="METHODS" NlmCategory="METHODS">Second section.</AbstractText>
        </Abstract>
        <Journal>
          <Title>Example Journal</Title>
          <JournalIssue><PubDate><Year>2024</Year><Month>Dec</Month></PubDate></JournalIssue>
        </Journal>
        <AuthorList>
          <Author><LastName>Smith</LastName><ForeName>Jane</ForeName></Author>
        </AuthorList>
        <PublicationTypeList>
          <PublicationType>Retracted Publication</PublicationType>
        </PublicationTypeList>
      </Article>
      <KeywordList><Keyword>development</Keyword></KeywordList>
      <MeshHeadingList>
        <MeshHeading><DescriptorName UI="D001">Humans</DescriptorName></MeshHeading>
      </MeshHeadingList>
    </MedlineCitation>
    <PubmedData>
      <ArticleIdList>
        <ArticleId IdType="pubmed">123</ArticleId>
        <ArticleId IdType="pmc">PMC456</ArticleId>
        <ArticleId IdType="doi">10.1/example</ArticleId>
      </ArticleIdList>
    </PubmedData>
  </PubmedArticle>
  <PubmedArticle>
    <MedlineCitation Status="Publisher">
      <PMID>789</PMID>
      <Article>
        <ArticleTitle>No abstract</ArticleTitle>
        <Journal>
          <Title>Other Journal</Title>
          <JournalIssue>
            <PubDate><MedlineDate>1998 Winter</MedlineDate></PubDate>
          </JournalIssue>
        </Journal>
      </Article>
    </MedlineCitation>
  </PubmedArticle>
</PubmedArticleSet>
"""


def test_parser_preserves_structured_abstract_ids_and_retraction() -> None:
    records = parse_pubmed_xml(PUBMED_XML)

    article = records[0]
    assert article["pmid"] == "123"
    assert article["pmcid_if_present"] == "PMC456"
    assert article["doi"] == "10.1/example"
    assert article["title"] == "Example structured article"
    assert article["abstract"] == "First section.\n\nSecond section."
    assert article["structured_abstract_sections"][0] == {
        "label": "BACKGROUND",
        "category": "BACKGROUND",
        "text": "First section.",
    }
    assert article["publication_year"] == 2024
    assert article["authors"] == ["Jane Smith"]
    assert article["mesh_terms"] == ["Humans"]
    assert article["is_retracted"] is True


def test_missing_abstract_is_valid() -> None:
    records = parse_pubmed_xml(PUBMED_XML)

    assert records[1]["pmid"] == "789"
    assert records[1]["abstract"] is None
    assert records[1]["has_abstract"] is False
    assert records[1]["publication_year"] == 1998


def test_batch_plan_is_deterministic_and_content_addressed() -> None:
    first = plan_batches(["3", "1", "2"], batch_size=2)
    second = plan_batches(["2", "3", "1"], batch_size=2)

    assert first == second
    assert first[0].pmids == ("1", "2")
    assert first[0].batch_id.startswith("batch_000001_")
    assert first[1].pmids == ("3",)
