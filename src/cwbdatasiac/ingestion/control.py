"""Tabela de controle `controle.ingestao_execucoes` no DuckDB do warehouse."""

from dataclasses import dataclass, fields
from datetime import date, datetime
from pathlib import Path

import duckdb

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
