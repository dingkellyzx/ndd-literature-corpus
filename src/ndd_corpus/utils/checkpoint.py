from __future__ import annotations

import sqlite3
from contextlib import closing
from datetime import UTC, datetime
from pathlib import Path

from ndd_corpus.utils.http import sha256_file

VALID_STATES = {"pending", "running", "complete", "failed"}


def _now() -> str:
    return datetime.now(UTC).isoformat()


class CheckpointStore:
    """Transactional task state for restartable pipeline stages."""

    def __init__(self, path: str | Path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._initialize()

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.path, timeout=30)
        connection.row_factory = sqlite3.Row
        return connection

    def _initialize(self) -> None:
        with closing(self._connect()) as connection:
            connection.execute("PRAGMA journal_mode=WAL")
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS tasks (
                    stage TEXT NOT NULL,
                    task_key TEXT NOT NULL,
                    status TEXT NOT NULL CHECK(status IN ('pending','running','complete','failed')),
                    artifact_path TEXT,
                    checksum TEXT,
                    error TEXT,
                    attempts INTEGER NOT NULL DEFAULT 0,
                    updated_at TEXT NOT NULL,
                    PRIMARY KEY(stage, task_key)
                )
                """
            )
            connection.commit()

    def ensure_task(self, stage: str, task_key: str) -> None:
        with closing(self._connect()) as connection:
            connection.execute(
                """
                INSERT OR IGNORE INTO tasks(stage, task_key, status, updated_at)
                VALUES (?, ?, 'pending', ?)
                """,
                (stage, task_key, _now()),
            )
            connection.commit()

    def claim(self, stage: str, task_key: str) -> bool:
        with closing(self._connect()) as connection:
            cursor = connection.execute(
                """
                UPDATE tasks
                SET status='running', attempts=attempts+1, error=NULL, updated_at=?
                WHERE stage=? AND task_key=? AND status IN ('pending','failed')
                """,
                (_now(), stage, task_key),
            )
            connection.commit()
            return cursor.rowcount == 1

    def complete(
        self,
        stage: str,
        task_key: str,
        *,
        artifact_path: str | Path | None = None,
        checksum: str | None = None,
    ) -> None:
        path_text = str(Path(artifact_path).resolve()) if artifact_path is not None else None
        with closing(self._connect()) as connection:
            cursor = connection.execute(
                """
                UPDATE tasks SET status='complete', artifact_path=?, checksum=?, updated_at=?
                WHERE stage=? AND task_key=? AND status='running'
                """,
                (path_text, checksum, _now(), stage, task_key),
            )
            if cursor.rowcount != 1:
                raise RuntimeError(f"cannot complete unclaimed task {stage}:{task_key}")
            connection.commit()

    def fail(self, stage: str, task_key: str, error: str) -> None:
        with closing(self._connect()) as connection:
            connection.execute(
                """
                UPDATE tasks SET status='failed', error=?, updated_at=?
                WHERE stage=? AND task_key=?
                """,
                (error[:2000], _now(), stage, task_key),
            )
            connection.commit()

    def reset_interrupted(self) -> int:
        with closing(self._connect()) as connection:
            cursor = connection.execute(
                "UPDATE tasks SET status='pending', updated_at=? WHERE status='running'",
                (_now(),),
            )
            connection.commit()
            return cursor.rowcount

    def status(self, stage: str, task_key: str) -> str | None:
        with closing(self._connect()) as connection:
            row = connection.execute(
                "SELECT status FROM tasks WHERE stage=? AND task_key=?",
                (stage, task_key),
            ).fetchone()
        return str(row["status"]) if row else None

    def is_complete(self, stage: str, task_key: str) -> bool:
        with closing(self._connect()) as connection:
            row = connection.execute(
                """
                SELECT status, artifact_path, checksum FROM tasks
                WHERE stage=? AND task_key=?
                """,
                (stage, task_key),
            ).fetchone()
            if row is None or row["status"] != "complete":
                return False
            if not row["artifact_path"]:
                return True
            path = Path(row["artifact_path"])
            valid = (
                path.is_file()
                and bool(row["checksum"])
                and sha256_file(path) == row["checksum"]
            )
            if not valid:
                connection.execute(
                    """
                    UPDATE tasks SET status='pending', artifact_path=NULL, checksum=NULL,
                    updated_at=? WHERE stage=? AND task_key=?
                    """,
                    (_now(), stage, task_key),
                )
                connection.commit()
            return valid

    def rows(self, stage: str | None = None) -> list[dict[str, object]]:
        query = "SELECT * FROM tasks"
        parameters: tuple[str, ...] = ()
        if stage is not None:
            query += " WHERE stage=?"
            parameters = (stage,)
        query += " ORDER BY stage, task_key"
        with closing(self._connect()) as connection:
            return [dict(row) for row in connection.execute(query, parameters).fetchall()]
