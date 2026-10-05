from __future__ import annotations

from pathlib import Path

import pytest

from ndd_corpus.config import Settings


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

