from __future__ import annotations

from pathlib import Path

import pytest
from pydantic import ValidationError

from ndd_corpus.config import PubmedConfig, RelevanceConfig, Settings


def _write_config(path: Path) -> None:
    path.parent.mkdir(parents=True)
    path.write_text(
        """
project:
  name: test-corpus
paths:
  data: data
  raw: data/raw
  interim: data/interim
  processed: data/processed
  logs: data/logs
debug:
  enabled: true
""".strip()
        + "\n",
        encoding="utf-8",
    )


def test_load_resolves_paths_from_repository_root(tmp_path: Path) -> None:
    config_path = tmp_path / "configs" / "default.yaml"
    _write_config(config_path)

    settings = Settings.load(config_path, env={"NCBI_EMAIL": "owner@example.org"})

    assert settings.project.name == "test-corpus"
    assert settings.paths.data == tmp_path / "data"
    assert settings.paths.processed == tmp_path / "data" / "processed"
    assert settings.debug.enabled is True


def test_live_ncbi_operations_require_email(tmp_path: Path) -> None:
    config_path = tmp_path / "configs" / "default.yaml"
    _write_config(config_path)
    settings = Settings.load(config_path, env={})

    with pytest.raises(ValueError, match="NCBI_EMAIL"):
        settings.require_ncbi_credentials()


def test_api_key_is_never_in_safe_configuration(tmp_path: Path) -> None:
    config_path = tmp_path / "configs" / "default.yaml"
    _write_config(config_path)
    settings = Settings.load(
        config_path,
        env={"NCBI_EMAIL": "owner@example.org", "NCBI_API_KEY": "top-secret"},
    )

    assert "top-secret" not in repr(settings)
    assert settings.safe_metadata()["ncbi_api_key_configured"] is True
    assert "ncbi_api_key" not in settings.safe_metadata()


def test_default_pubmed_window_is_2010_through_2020() -> None:
    defaults = PubmedConfig()
    repository_root = Path(__file__).resolve().parents[2]
    settings = Settings.load(
        repository_root / "configs/default.yaml",
        env={"NCBI_EMAIL": "owner@example.org"},
    )

    assert (defaults.start_year, defaults.end_year) == (2010, 2020)
    assert (settings.pubmed.start_year, settings.pubmed.end_year) == (2010, 2020)


def test_relevance_defaults_are_conservative_and_match_default_yaml() -> None:
    defaults = RelevanceConfig()
    repository_root = Path(__file__).resolve().parents[2]
    settings = Settings.load(
        repository_root / "configs/default.yaml",
        env={"NCBI_EMAIL": "owner@example.org"},
    )

    assert defaults.backend == "ollama"
    assert defaults.base_url == "http://127.0.0.1:11434/v1"
    assert defaults.model == "qwen3:14b"
    assert defaults.temperature == 0.0
    assert defaults.timeout_seconds == 120.0
    assert defaults.max_retries == 2
    assert defaults.think is False
    assert defaults.keep_labels == ["HIGH", "POSSIBLE"]
    assert settings.relevance == defaults


@pytest.mark.parametrize(
    ("field", "value"),
    [("timeout_seconds", 0), ("max_retries", -1)],
)
def test_relevance_config_rejects_invalid_retry_limits(field: str, value: int) -> None:
    with pytest.raises(ValidationError):
        RelevanceConfig(**{field: value})


def test_relevance_config_rejects_unknown_keep_label() -> None:
    with pytest.raises(ValidationError):
        RelevanceConfig(keep_labels=["HIGH", "MAYBE"])  # type: ignore[list-item]
