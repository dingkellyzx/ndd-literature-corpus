from __future__ import annotations

from pathlib import Path

from ndd_corpus.utils.checkpoint import CheckpointStore
from ndd_corpus.utils.http import atomic_write_bytes, sha256_file


def test_atomic_write_has_no_partial_file(tmp_path: Path) -> None:
    destination = tmp_path / "raw" / "batch.xml.gz"

    atomic_write_bytes(destination, b"complete payload")

    assert destination.read_bytes() == b"complete payload"
    assert not list(destination.parent.glob("*.part"))


def test_running_work_is_reset_to_pending_after_restart(tmp_path: Path) -> None:
    store = CheckpointStore(tmp_path / "checkpoints.sqlite")
    store.ensure_task("pubmed-fetch", "batch-1")
    assert store.claim("pubmed-fetch", "batch-1") is True

    assert store.reset_interrupted() == 1

    assert store.status("pubmed-fetch", "batch-1") == "pending"


def test_completed_artifact_is_skipped_only_when_checksum_matches(tmp_path: Path) -> None:
    artifact = tmp_path / "batch.xml.gz"
    atomic_write_bytes(artifact, b"valid")
    store = CheckpointStore(tmp_path / "checkpoints.sqlite")
    store.ensure_task("pubmed-fetch", "batch-1")
    assert store.claim("pubmed-fetch", "batch-1") is True
    store.complete(
        "pubmed-fetch",
        "batch-1",
        artifact_path=artifact,
        checksum=sha256_file(artifact),
    )

    assert store.is_complete("pubmed-fetch", "batch-1") is True

    artifact.write_bytes(b"corrupt")
    assert store.is_complete("pubmed-fetch", "batch-1") is False
    assert store.status("pubmed-fetch", "batch-1") == "pending"

