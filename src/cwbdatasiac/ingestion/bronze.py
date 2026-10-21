"""Converte o CSV bruto em Parquet na camada Bronze, particionado por data do snapshot.

Todas as colunas ficam como texto (a tipagem é feita no dbt). São acrescentadas
`snapshot_data` e `linha` (posição no arquivo, a partir de 1), que formam a chave
técnica dentro do snapshot; ver ADR 0001.
"""

from datetime import date
from pathlib import Path

import pyarrow as pa
import pyarrow.csv as pacsv
import pyarrow.parquet as pq

from cwbdatasiac.config import EXPECTED_COLUMNS


def partition_path(bronze_dir: Path, snapshot_date: date) -> Path:
    return bronze_dir / f"snapshot_data={snapshot_date.isoformat()}" / "part-0.parquet"


def read_csv(path: Path) -> pa.Table:
    """Lê as colunas nomeadas como texto. O Arrow descarta o BOM UTF-8 e aceita CRLF."""
    return pacsv.read_csv(
        path,
        parse_options=pacsv.ParseOptions(delimiter=";"),
        convert_options=pacsv.ConvertOptions(
            column_types=dict.fromkeys(EXPECTED_COLUMNS, pa.string()),
            include_columns=list(EXPECTED_COLUMNS),
            strings_can_be_null=True,
        ),
    )


def write_bronze(table: pa.Table, bronze_dir: Path, snapshot_date: date) -> Path:
    """Escreve (ou sobrescreve, de forma atômica) a partição do snapshot."""
    rows = table.num_rows
    table = table.append_column(
        "snapshot_data", pa.array([snapshot_date] * rows, type=pa.date32())
    ).append_column("linha", pa.array(range(1, rows + 1), type=pa.int32()))

    dest = partition_path(bronze_dir, snapshot_date)
    dest.parent.mkdir(parents=True, exist_ok=True)
    tmp = dest.with_name(dest.name + ".tmp")
    pq.write_table(table, tmp, compression="zstd")
    tmp.replace(dest)
    return dest
