from __future__ import annotations

import logging
from pathlib import Path


class SecretRedactionFilter(logging.Filter):
    def __init__(self, secrets: list[str | None]):
        super().__init__()
        self.secrets = [secret for secret in secrets if secret]

    def filter(self, record: logging.LogRecord) -> bool:
        message = record.getMessage()
        for secret in self.secrets:
            message = message.replace(secret, "[REDACTED]")
        record.msg = message
        record.args = ()
        return True


def configure_logging(log_file: str | Path, *, secrets: list[str | None] | None = None) -> None:
    destination = Path(log_file)
    destination.parent.mkdir(parents=True, exist_ok=True)
    handlers: list[logging.Handler] = [logging.StreamHandler(), logging.FileHandler(destination)]
    redaction = SecretRedactionFilter(secrets or [])
    for handler in handlers:
        handler.addFilter(redaction)
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
        handlers=handlers,
        force=True,
    )

