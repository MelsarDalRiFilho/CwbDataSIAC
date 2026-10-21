import json
import logging
from datetime import date

import httpx
import pytest
import respx

from cwbdatasiac import config
from cwbdatasiac.ingestion import bronze, control
from cwbdatasiac.ingestion.pipeline import prune_raw, run_ingestion
from cwbdatasiac.observability import configure_logging
from cwbdatasiac.observability.logging import LOG_FILE_NAME
from tests.conftest import HEADER, make_csv, make_manifest

D19 = "2026-10-19_156_-_Base_de_Dados.csv"
D20 = "2026-10-20_156_-_Base_de_Dados.csv"
URL19 = config.MIRROR_BASE_URL + D19
URL20 = config.MIRROR_BASE_URL + D20


@pytest.fixture
def mock_source():
    with respx.mock(assert_all_called=False) as router:
        router.get(config.MANIFEST_URL).respond(text=make_manifest(D19, D20))
        yield router


def _serve(router, url, content: bytes, status: int = 200):
    return router.get(url).respond(status, content=content, headers={"content-type": "text/csv"})


def _ingest(settings, snapshot=None, **kwargs):
    with httpx.Client() as client:
        return run_ingestion(settings, client, snapshot, **kwargs)


def _runs(settings):
    with control.connect(settings.warehouse_path) as con:
        return con.execute(
            "select status, etapa_falha, linhas from controle.ingestao_execucoes order by inicio"
        ).fetchall()


def test_success_writes_bronze_and_control_row(settings, mock_source):
    _serve(mock_source, URL20, make_csv(rows=5))

    execucao = _ingest(settings)

    assert execucao.status == "sucesso"
    assert execucao.snapshot_data == date(2026, 10, 20)
    assert execucao.fonte_descoberta == "manifesto"
    assert bronze.partition_path(settings.bronze_dir, date(2026, 10, 20)).exists()
    assert (settings.raw_dir / D20).exists()
    assert _runs(settings) == [("sucesso", None, 5)]


def test_second_run_is_idempotent(settings, mock_source):
    route = _serve(mock_source, URL20, make_csv(rows=5))

    _ingest(settings)
    second = _ingest(settings)

    assert second.status == "sem_novidade"
    assert route.call_count == 1
    assert [r[0] for r in _runs(settings)] == ["sucesso", "sem_novidade"]


def test_force_reloads_snapshot(settings, mock_source):
    route = _serve(mock_source, URL20, make_csv(rows=5))

    _ingest(settings)
    assert _ingest(settings, force=True).status == "sucesso"
    assert route.call_count == 2


def test_http_failure_is_logged_and_recorded(settings, mock_source, tmp_path):
    configure_logging("INFO", tmp_path / "logs")
    _serve(mock_source, URL20, b"", status=500)

    execucao = _ingest(settings)

    assert execucao.status == "falha"
    assert execucao.etapa_falha == "download"
    assert _runs(settings) == [("falha", "download", None)]
    entries = [
        json.loads(line) for line in (tmp_path / "logs" / LOG_FILE_NAME).read_text().splitlines()
    ]
    error = next(e for e in entries if e["level"] == "ERROR")
    assert error["run_id"] == execucao.run_id
    assert error["etapa"] == "download"


def test_truncated_file_goes_to_quarantine(settings, mock_source):
    _serve(mock_source, URL20, make_csv(rows=1))
    small = settings.__class__(**{**settings.__dict__, "min_bytes": 10_000})

    execucao = _ingest(small)

    assert (execucao.status, execucao.etapa_falha) == ("falha", "conteudo")
    assert not (small.raw_dir / D20).exists()
    assert (small.quarantine_dir / f"{execucao.run_id}_{D20}").exists()


def test_missing_column_fails_with_clear_message(settings, mock_source):
    _serve(mock_source, URL20, make_csv(header=HEADER.replace("Situacao;", "")))

    execucao = _ingest(settings)

    assert execucao.etapa_falha == "cabecalho"
    assert "Situacao" in execucao.mensagem
    assert list(settings.quarantine_dir.iterdir())


def test_malformed_csv_fails_on_read(settings, mock_source):
    _serve(mock_source, URL20, make_csv(row="a;b;c;d;e;f;g;h;i;j;k;l;m;n;"))

    assert _ingest(settings).etapa_falha == "leitura"


def test_shrinking_snapshot_is_not_promoted(settings, mock_source):
    _serve(mock_source, URL19, make_csv(rows=5))
    _serve(mock_source, URL20, make_csv(rows=3))

    _ingest(settings, date(2026, 10, 19))
    execucao = _ingest(settings, date(2026, 10, 20))

    assert execucao.etapa_falha == "volume"
    assert not bronze.partition_path(settings.bronze_dir, date(2026, 10, 20)).exists()


def test_unchanged_content_on_new_date_is_skipped(settings, mock_source):
    _serve(mock_source, URL19, make_csv(rows=5))
    _serve(mock_source, URL20, make_csv(rows=5))

    _ingest(settings, date(2026, 10, 19))
    execucao = _ingest(settings, date(2026, 10, 20))

    assert execucao.status == "sem_novidade"
    assert "idêntico" in execucao.mensagem
    assert not (settings.raw_dir / D20).exists()


def test_unexpected_error_is_recorded(settings, mock_source, monkeypatch, caplog):
    _serve(mock_source, URL20, make_csv(rows=5))

    def boom(*args, **kwargs):
        raise RuntimeError("disco cheio")

    monkeypatch.setattr(bronze, "write_bronze", boom)
    with caplog.at_level(logging.ERROR):
        execucao = _ingest(settings)

    assert (execucao.status, execucao.etapa_falha) == ("falha", "inesperado")
    assert "disco cheio" in execucao.mensagem
    assert any(r.exc_info for r in caplog.records)


def test_prune_raw_keeps_most_recent_dates(settings):
    settings.raw_dir.mkdir(parents=True)
    for day in range(15, 21):
        (settings.raw_dir / f"2026-10-{day}_156_-_Base_de_Dados.csv").write_text("x")
    (settings.raw_dir / "outro.csv").write_text("x")

    removed = prune_raw(settings)

    assert len(removed) == 3
    assert sorted(p.name for p in settings.raw_dir.iterdir()) == [
        "2026-10-18_156_-_Base_de_Dados.csv",
        "2026-10-19_156_-_Base_de_Dados.csv",
        "2026-10-20_156_-_Base_de_Dados.csv",
        "outro.csv",
    ]
