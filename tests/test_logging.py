import json
import logging

import pytest

from cwbdatasiac.observability import configure_logging, get_run_id, run_context
from cwbdatasiac.observability.logging import LOG_FILE_NAME


@pytest.fixture(autouse=True)
def _restore_root_logger():
    root = logging.getLogger()
    handlers, level = root.handlers[:], root.level
    yield
    for handler in root.handlers[:]:
        root.removeHandler(handler)
        handler.close()
    for handler in handlers:
        root.addHandler(handler)
    root.setLevel(level)


def _read_lines(log_dir):
    return [json.loads(line) for line in (log_dir / LOG_FILE_NAME).read_text().splitlines()]


def test_writes_json_with_run_id_and_extra_fields(tmp_path):
    configure_logging("INFO", tmp_path)

    with run_context("abc123"):
        logging.getLogger("teste").info(
            "download concluído", extra={"etapa": "download", "bytes": 10}
        )

    [entry] = _read_lines(tmp_path)
    assert entry["message"] == "download concluído"
    assert entry["level"] == "INFO"
    assert entry["logger"] == "teste"
    assert entry["run_id"] == "abc123"
    assert entry["etapa"] == "download"
    assert entry["bytes"] == 10


def test_run_id_is_none_outside_context(tmp_path):
    configure_logging("INFO", tmp_path)
    logging.getLogger("teste").warning("sem execução")

    assert _read_lines(tmp_path)[0]["run_id"] is None


def test_run_context_generates_and_restores_run_id():
    assert get_run_id() is None
    with run_context() as run_id:
        assert len(run_id) == 32
        assert get_run_id() == run_id
    assert get_run_id() is None


def test_exception_is_serialized(tmp_path):
    configure_logging("INFO", tmp_path)
    try:
        raise ValueError("falhou")
    except ValueError:
        logging.getLogger("teste").exception("erro na captura")

    entry = _read_lines(tmp_path)[0]
    assert entry["level"] == "ERROR"
    assert "ValueError: falhou" in entry["exception"]


def test_level_filters_messages(tmp_path):
    configure_logging("warning", tmp_path)
    logging.getLogger("teste").info("ignorada")
    logging.getLogger("teste").error("registrada")

    assert [e["message"] for e in _read_lines(tmp_path)] == ["registrada"]


def test_reconfiguring_does_not_duplicate_handlers(tmp_path):
    configure_logging("INFO", tmp_path)
    configure_logging("INFO", tmp_path)
    logging.getLogger("teste").info("uma vez")

    assert len(_read_lines(tmp_path)) == 1


def test_console_only_when_log_dir_is_none(tmp_path, capsys):
    configure_logging("INFO", None)
    logging.getLogger("teste").info("só console")

    assert json.loads(capsys.readouterr().err)["message"] == "só console"
    assert not (tmp_path / LOG_FILE_NAME).exists()
