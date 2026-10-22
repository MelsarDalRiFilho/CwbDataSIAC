"""Acesso somente leitura ao warehouse, com uma conexão curta por consulta.

O DuckDB não permite leitores de outro processo enquanto a ingestão ou o dbt
gravam. Abrir e fechar a cada consulta mantém a janela de conflito em
milissegundos; se o arquivo estiver travado, `WarehouseUnavailable` vira 503.
"""

from collections.abc import Sequence
from pathlib import Path
from typing import Any

import duckdb


class WarehouseUnavailable(Exception):
    """Warehouse travado pelo pipeline ou ainda não criado."""


class Warehouse:
    def __init__(self, path: Path) -> None:
        self.path = path

    def query(self, sql: str, params: Sequence[Any] | None = None) -> list[dict[str, Any]]:
        try:
            con = duckdb.connect(str(self.path), read_only=True)
        except duckdb.IOException as exc:
            raise WarehouseUnavailable(str(exc)) from exc
        try:
            cursor = con.execute(sql, params or [])
            columns = [d[0] for d in cursor.description]
            return [dict(zip(columns, row, strict=True)) for row in cursor.fetchall()]
        finally:
            con.close()

    def query_one(self, sql: str, params: Sequence[Any] | None = None) -> dict[str, Any] | None:
        rows = self.query(sql, params)
        return rows[0] if rows else None
