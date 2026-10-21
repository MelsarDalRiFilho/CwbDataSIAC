from datetime import date

import pyarrow.parquet as pq

from cwbdatasiac.config import EXPECTED_COLUMNS
from cwbdatasiac.ingestion.bronze import partition_path, read_csv, write_bronze
from tests.conftest import make_csv

SNAPSHOT = date(2026, 10, 20)


def test_read_csv_handles_bom_and_trailing_column(tmp_path):
    path = tmp_path / "f.csv"
    path.write_bytes(make_csv(rows=3))

    table = read_csv(path)

    assert table.column_names == list(EXPECTED_COLUMNS)
    assert table.num_rows == 3
    assert table.column("Tipo")[0].as_py() == "Solicitação"


def test_empty_values_become_null(tmp_path):
    path = tmp_path / "f.csv"
    path.write_bytes(make_csv(rows=1, row="A;B;01/01/2026;C;D;Aberto;;;;;Telefone;"))

    row = read_csv(path).to_pylist()[0]

    assert row["Bairro"] is None
    assert row["DataResposta"] is None


def test_write_bronze_adds_technical_key_and_overwrites(tmp_path):
    csv = tmp_path / "f.csv"
    csv.write_bytes(make_csv(rows=4))
    bronze_dir = tmp_path / "bronze"

    write_bronze(read_csv(csv), bronze_dir, SNAPSHOT)
    dest = write_bronze(read_csv(csv), bronze_dir, SNAPSHOT)

    assert dest == partition_path(bronze_dir, SNAPSHOT)
    assert dest.parent.name == "snapshot_data=2026-10-20"
    table = pq.read_table(dest)
    assert table.num_rows == 4
    assert table.column("linha").to_pylist() == [1, 2, 3, 4]
    assert set(table.column("snapshot_data").to_pylist()) == {SNAPSHOT}
    assert [p.name for p in dest.parent.iterdir()] == ["part-0.parquet"]
