"""Warehouse real para os testes da API: Bronze sintética → dbt build (em subprocesso)."""

import subprocess
import sys
from datetime import UTC, date, datetime

import pyarrow as pa
import pytest
from fastapi.testclient import TestClient

from cwbdatasiac.api.main import create_app
from cwbdatasiac.config import EXPECTED_COLUMNS
from cwbdatasiac.ingestion import control
from cwbdatasiac.ingestion.bronze import write_bronze
from cwbdatasiac.validation.contracts import ResultadoContrato, Violacao

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
ANSWERED = {"Situacao": "Concluído", "DataResposta": "11/10/2026"}  # 10 dias
HEALTH_OPEN = {
    "Orgao": "SECRETARIA MUNICIPAL DA SAÚDE",
    "Assunto": "Unidade de Saúde",
    "Subdivisao": "Atendimento",
    "DataCriacao": "15/09/2026",
    "Tipo": "Reclamação",
    "Origem": "Telefone",
    "Bairro": None,
    "Regional": None,
}
HEALTH_ANSWERED = {
    **HEALTH_OPEN,
    "DataCriacao": "02/10/2026",
    "Situacao": "Concluído",
    "DataResposta": "04/10/2026",  # 2 dias
    "Bairro": "CENTRO",
    "Regional": "Unidade Regional Matriz",
}

# Último snapshot (21/10): 5 solicitações, 2 respondidas, 3 pendentes. Duas linhas
# idênticas de propósito (ADR 0001).
SNAPSHOT_21 = [{}, {}, ANSWERED, HEALTH_OPEN, HEALTH_ANSWERED]
SNAPSHOT_20 = [{}, ANSWERED, HEALTH_OPEN]

BUILD_SCRIPT = """
import sys
from pathlib import Path
from cwbdatasiac.transform import run_dbt
data_dir, target, logs = map(Path, sys.argv[1:4])
ok = run_dbt(["build"], data_dir, ["--target-path", str(target), "--log-path", str(logs)])
sys.exit(0 if ok else 1)
"""


def _write_snapshot(data_dir, snapshot: date, rows: list[dict]) -> None:
    full = [{**BASE, **r} for r in rows]
    table = pa.table({c: pa.array([r[c] for r in full], pa.string()) for c in EXPECTED_COLUMNS})
    write_bronze(table, data_dir / "bronze" / "siac156", snapshot)


def _execucao(run_id: str, snapshot: date, status: str, minute: int, **kwargs):
    inicio = datetime(2026, 10, 22, 6, minute, tzinfo=UTC)
    return control.Execucao(
        run_id=run_id,
        inicio=inicio,
        fim=inicio,
        status=status,
        snapshot_data=snapshot,
        arquivo=f"{snapshot}_156_-_Base_de_Dados.csv",
        **kwargs,
    )


def _write_control(data_dir) -> None:
    alerta = ResultadoContrato(
        date(2026, 10, 21),
        linhas=5,
        tolerancia=0.001,
        violacoes=[Violacao("dominio_conhecido", "Origem", "alerta", 1, ["WhatsApp"])],
    )
    with control.connect(data_dir / "warehouse.duckdb") as con:
        control.save(con, _execucao("r1", date(2026, 10, 20), "sucesso", 1, linhas=3))
        control.save(con, _execucao("r2", date(2026, 10, 21), "sucesso", 2, linhas=5))
        control.save(con, _execucao("r3", date(2026, 10, 22), "falha", 3, etapa_falha="download"))
        control.save_violations(con, "r2", alerta)


@pytest.fixture(scope="session")
def warehouse_dir(tmp_path_factory):
    root = tmp_path_factory.mktemp("api")
    data_dir = root / "data"
    _write_snapshot(data_dir, date(2026, 10, 20), SNAPSHOT_20)
    _write_snapshot(data_dir, date(2026, 10, 21), SNAPSHOT_21)
    _write_control(data_dir)
    # Subprocesso: o dbt-duckdb deixa o banco aberto no processo que o executa.
    subprocess.run(
        [sys.executable, "-c", BUILD_SCRIPT, data_dir, root / "target", root / "logs"],
        check=True,
        capture_output=True,
    )
    return data_dir


@pytest.fixture(scope="session")
def client(warehouse_dir):
    return TestClient(create_app(warehouse_dir))
