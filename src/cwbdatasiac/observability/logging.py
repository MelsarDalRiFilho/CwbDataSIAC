"""Logging estruturado em JSON com `run_id` propagado por contextvar.

Toda mensagem emitida dentro de `run_context()` carrega o mesmo `run_id`, o que
permite cruzar o log com o registro da execução em `ingestao_execucoes`.
Campos extras passados em `extra={...}` vão para o JSON como chaves de primeiro nível.
"""

import json
import logging
import uuid
from collections.abc import Iterator
from contextlib import contextmanager
from contextvars import ContextVar
from datetime import UTC, datetime
from logging.handlers import RotatingFileHandler
from pathlib import Path

LOG_FILE_NAME = "cwbdatasiac.log"

_run_id: ContextVar[str | None] = ContextVar("run_id", default=None)

# Atributos padrão de LogRecord; o que não estiver aqui veio de `extra`.
_RESERVED = set(logging.makeLogRecord({}).__dict__) | {"message", "asctime", "run_id"}


def get_run_id() -> str | None:
    return _run_id.get()


@contextmanager
def run_context(run_id: str | None = None) -> Iterator[str]:
    """Define o `run_id` da execução corrente (gera um uuid4 se não for informado)."""
    token = _run_id.set(run_id or uuid.uuid4().hex)
    try:
        yield _run_id.get()
    finally:
        _run_id.reset(token)


class RunIdFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        record.run_id = _run_id.get()
        return True


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        payload = {
            "ts": datetime.fromtimestamp(record.created, UTC).isoformat(timespec="milliseconds"),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
            "run_id": getattr(record, "run_id", None),
        }
        payload.update({k: v for k, v in record.__dict__.items() if k not in _RESERVED})
        if record.exc_info:
            payload["exception"] = self.formatException(record.exc_info)
        return json.dumps(payload, ensure_ascii=False, default=str)


def configure_logging(level: str = "INFO", log_dir: Path | None = Path("logs")) -> None:
    """Configura o logger raiz: JSON no console e, se `log_dir` for dado, em arquivo rotativo."""
    formatter = JsonFormatter()
    run_filter = RunIdFilter()

    handlers: list[logging.Handler] = [logging.StreamHandler()]
    if log_dir is not None:
        log_dir.mkdir(parents=True, exist_ok=True)
        handlers.append(
            RotatingFileHandler(
                log_dir / LOG_FILE_NAME, maxBytes=5_000_000, backupCount=5, encoding="utf-8"
            )
        )

    root = logging.getLogger()
    for handler in root.handlers[:]:
        root.removeHandler(handler)
        handler.close()
    for handler in handlers:
        handler.setFormatter(formatter)
        handler.addFilter(run_filter)
        root.addHandler(handler)
    root.setLevel(level.upper())
