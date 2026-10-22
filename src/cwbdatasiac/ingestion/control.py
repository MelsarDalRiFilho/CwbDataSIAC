"""Tabelas de controle no DuckDB do warehouse: execuções da ingestão e violações do contrato."""

from dataclasses import dataclass, fields
from datetime import date, datetime
from pathlib import Path

import duckdb

from cwbdatasiac.validation.contracts import ResultadoContrato

DDL = """
create schema if not exists controle;
create table if not exists controle.ingestao_execucoes (
    run_id            varchar primary key,
    snapshot_data     date,
    arquivo           varchar,
    url               varchar,
    fonte_descoberta  varchar,
    inicio            timestamptz not null,
    fim               timestamptz,
    status            varchar not null,  -- em_andamento | sucesso | sem_novidade | falha
    etapa_falha       varchar,
    mensagem          varchar,
    bytes             bigint,
    linhas            bigint,
    sha256            varchar
);
create table if not exists controle.contrato_violacoes (
    run_id         varchar not null,
    snapshot_data  date not null,
    regra          varchar not null,
    coluna         varchar,
    severidade     varchar not null,  -- bloqueante | alerta
    linhas         bigint not null,
    exemplos       varchar[]
);
"""


@dataclass
class Execucao:
    run_id: str
    inicio: datetime
    status: str = "em_andamento"
    snapshot_data: date | None = None
    arquivo: str | None = None
    url: str | None = None
    fonte_descoberta: str | None = None
    fim: datetime | None = None
    etapa_falha: str | None = None
    mensagem: str | None = None
    bytes: int | None = None
    linhas: int | None = None
    sha256: str | None = None


_COLUMNS = [f.name for f in fields(Execucao)]


def connect(path: Path) -> duckdb.DuckDBPyConnection:
    path.parent.mkdir(parents=True, exist_ok=True)
    con = duckdb.connect(str(path))
    con.execute(DDL)
    return con


def save(con: duckdb.DuckDBPyConnection, execucao: Execucao) -> None:
    """Insere ou atualiza a execução (upsert por `run_id`)."""
    placeholders = ", ".join("?" for _ in _COLUMNS)
    updates = ", ".join(f"{c} = excluded.{c}" for c in _COLUMNS if c != "run_id")
    con.execute(
        f"insert into controle.ingestao_execucoes ({', '.join(_COLUMNS)}) values ({placeholders})"
        f" on conflict (run_id) do update set {updates}",
        [getattr(execucao, c) for c in _COLUMNS],
    )


def last_success(
    con: duckdb.DuckDBPyConnection, before: date | None = None
) -> tuple[date, int, str] | None:
    """Último snapshot carregado com sucesso (data, linhas, sha256), anterior a `before` se dado."""
    row = con.execute(
        """select snapshot_data, linhas, sha256 from controle.ingestao_execucoes
           where status = 'sucesso' and (? is null or snapshot_data < ?)
           order by snapshot_data desc, fim desc limit 1""",
        [before, before],
    ).fetchone()
    return (row[0], row[1], row[2]) if row else None


def success_for(con: duckdb.DuckDBPyConnection, snapshot_date: date) -> bool:
    row = con.execute(
        """select count(*) from controle.ingestao_execucoes
           where status = 'sucesso' and snapshot_data = ?""",
        [snapshot_date],
    ).fetchone()
    return bool(row and row[0])


def save_violations(
    con: duckdb.DuckDBPyConnection, run_id: str, resultado: ResultadoContrato
) -> None:
    con.executemany(
        "insert into controle.contrato_violacoes values (?, ?, ?, ?, ?, ?, ?)",
        [
            [run_id, resultado.snapshot_data, v.regra, v.coluna, v.severidade, v.linhas, v.exemplos]
            for v in resultado.violacoes
        ],
    )
