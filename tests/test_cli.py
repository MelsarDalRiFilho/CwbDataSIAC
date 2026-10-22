from datetime import UTC, date, datetime

import pytest
from typer.testing import CliRunner

from cwbdatasiac import __version__, cli
from cwbdatasiac.cli import app
from cwbdatasiac.ingestion.control import Execucao

runner = CliRunner()


def test_version(tmp_path):
    result = runner.invoke(app, ["--log-dir", str(tmp_path), "version"])

    assert result.exit_code == 0
    assert result.stdout.strip() == __version__


def test_callback_creates_log_dir(tmp_path):
    log_dir = tmp_path / "logs"
    runner.invoke(app, ["--log-dir", str(log_dir), "version"])

    assert log_dir.is_dir()


@pytest.fixture
def fake_ingestion(monkeypatch):
    calls = {}

    def fake(settings, client, snapshot_date, *, force):
        calls.update(settings=settings, snapshot_date=snapshot_date, force=force)
        return calls["result"]

    monkeypatch.setattr(cli, "run_ingestion", fake)
    return calls


def _execucao(status, **kwargs):
    return Execucao(run_id="r1", inicio=datetime.now(UTC), status=status, **kwargs)


def test_ingest_success_exits_zero_and_passes_options(tmp_path, fake_ingestion):
    fake_ingestion["result"] = _execucao("sucesso", arquivo="f.csv")

    result = runner.invoke(
        app,
        [
            "--log-dir", str(tmp_path / "logs"),
            "ingest", "--data", "2026-10-19", "--forcar",
            "--data-dir", str(tmp_path), "--no-navegador", "--manter-csv-dias", "5",
        ],
    )  # fmt: skip

    assert result.exit_code == 0
    assert "sucesso: f.csv (r1)" in result.stdout
    assert fake_ingestion["snapshot_date"] == date(2026, 10, 19)
    assert fake_ingestion["force"] is True
    assert fake_ingestion["settings"].use_browser is False
    assert fake_ingestion["settings"].keep_raw_days == 5


def test_ingest_failure_exits_nonzero(tmp_path, fake_ingestion):
    fake_ingestion["result"] = _execucao("falha", etapa_falha="download", mensagem="HTTP 500")

    result = runner.invoke(app, ["--log-dir", str(tmp_path), "ingest"])

    assert result.exit_code == 1
    assert "etapa download: HTTP 500" in result.stderr


@pytest.mark.parametrize(
    ("args", "expected_command"),
    [
        (["transform"], ["build"]),
        (["transform", "--full-refresh"], ["build", "--full-refresh"]),
        (["docs"], ["docs", "generate", "--static"]),
    ],
)
@pytest.mark.parametrize("success", [True, False])
def test_dbt_commands(tmp_path, monkeypatch, args, expected_command, success):
    calls = []
    monkeypatch.setattr(cli, "run_dbt", lambda cmd, data_dir: calls.append(cmd) or success)

    result = runner.invoke(app, ["--log-dir", str(tmp_path), *args])

    assert calls == [expected_command]
    assert result.exit_code == (0 if success else 1)
