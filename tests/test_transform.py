"""Roda o projeto dbt de verdade sobre uma Bronze sintética (é o `dbt build` do CI)."""

import os
from datetime import date

import duckdb
import pyarrow as pa
import pytest

from cwbdatasiac.config import EXPECTED_COLUMNS
from cwbdatasiac.ingestion.bronze import write_bronze
from cwbdatasiac.transform import DATA_DIR_ENV, run_dbt

BASE = {
    "Tipo": "Solicitação",
    "Orgao": "Secretaria Municipal do Meio Ambiente",
    "DataCriacao": "01/10/2026",
    "Assunto": "Coleta",
    "Subdivisao": "Entulhos",
    "Situacao": "Aberto",
    "Logradouro": "Rua Exemplo",
    "Bairro": "XAXIM",
    "Regional": "Unidade Regional Boqueirao",
    "DataResposta": None,
    "Origem": "App 156",
}
ANSWERED = {"Situacao": "Concluído", "DataResposta": "11/10/2026"}
HEALTH = {"Orgao": "SECRETARIA MUNICIPAL DA SAÚDE", "Bairro": None, "Regional": None}

pytestmark = pytest.mark.slow


def _write_snapshot(data_dir, snapshot: date, rows: list[dict]) -> None:
    full = [{**BASE, **r} for r in rows]
    table = pa.table({c: pa.array([r[c] for r in full], pa.string()) for c in EXPECTED_COLUMNS})
    write_bronze(table, data_dir / "bronze" / "siac156", snapshot)


def _build(data_dir, tmp_path, *command: str) -> bool:
    extra = ["--target-path", str(tmp_path / "target"), "--log-path", str(tmp_path / "dbt_logs")]
    return run_dbt(list(command or ["build"]), data_dir, extra)


def _query(data_dir, sql: str):
    # O dbt-duckdb mantém o banco aberto no processo; abrir em read_only (outra
    # configuração) seria recusado pelo DuckDB.
    with duckdb.connect(str(data_dir / "warehouse.duckdb")) as con:
        return con.execute(sql).fetchall()


@pytest.fixture
def data_dir(tmp_path):
    path = tmp_path / "data"
    # Duas linhas idênticas de propósito: são solicitações distintas (ADR 0001).
    _write_snapshot(path, date(2026, 10, 20), [{}, {}, ANSWERED, HEALTH])
    _write_snapshot(path, date(2026, 10, 21), [{}, {}, ANSWERED, ANSWERED, HEALTH])
    return path


def test_build_models_latest_snapshot_and_history(data_dir, tmp_path):
    assert _build(data_dir, tmp_path)

    assert _query(data_dir, "select count(*) from marts.fct_solicitacoes") == [(5,)]
    assert _query(
        data_dir,
        "select snapshot_data, sum(quantidade)::int, sum(respondidas)::int "
        "from marts.fct_snapshot_agregado group by 1 order by 1",
    ) == [(date(2026, 10, 20), 4, 1), (date(2026, 10, 21), 5, 2)]
    assert _query(data_dir, "select orgao from marts.dim_orgao order by 1") == [
        ("Secretaria Municipal da Saúde",),
        ("Secretaria Municipal do Meio Ambiente",),
    ]
    assert ("NÃO INFORMADO", "Não informada") in _query(
        data_dir, "select bairro, regional from marts.dim_localidade"
    )
    columns = [
        c
        for (c,) in _query(
            data_dir,
            "select column_name from duckdb_columns() where table_name = 'fct_solicitacoes'",
        )
    ]
    assert "logradouro" not in columns


def test_incremental_history_appends_new_snapshot(data_dir, tmp_path):
    assert _build(data_dir, tmp_path)
    _write_snapshot(data_dir, date(2026, 10, 22), [{}, ANSWERED, ANSWERED, ANSWERED])

    assert _build(data_dir, tmp_path)

    assert _query(
        data_dir,
        "select snapshot_data, sum(quantidade)::int from marts.fct_snapshot_agregado "
        "group by 1 order by 1",
    ) == [(date(2026, 10, 20), 4), (date(2026, 10, 21), 5), (date(2026, 10, 22), 4)]
    assert _query(data_dir, "select count(*) from marts.fct_solicitacoes") == [(4,)]


def test_failure_returns_false_and_restores_env(tmp_path, monkeypatch):
    monkeypatch.setenv(DATA_DIR_ENV, "valor-anterior")

    assert not _build(tmp_path / "vazio", tmp_path)  # sem Bronze, a fonte não existe
    assert os.environ[DATA_DIR_ENV] == "valor-anterior"
