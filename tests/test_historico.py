from datetime import date

import pyarrow as pa
from typer.testing import CliRunner

from cwbdatasiac.cli import app
from cwbdatasiac.historico import asset_name, exportar, importar
from cwbdatasiac.ingestion.bronze import partition_path, write_bronze


def _bronze(bronze_dir, *snapshots):
    for snapshot in snapshots:
        write_bronze(pa.table({"Tipo": ["Elogio"]}), bronze_dir, snapshot)


def test_round_trip_through_assets(tmp_path):
    origem, assets, restaurada = tmp_path / "bronze", tmp_path / "assets", tmp_path / "nova"
    _bronze(origem, date(2026, 10, 20), date(2026, 10, 21))

    exportados = exportar(origem, assets, existentes=set())
    importados = importar(assets, restaurada)

    assert [p.name for p in exportados] == [
        "bronze_siac156_2026-10-20.parquet",
        "bronze_siac156_2026-10-21.parquet",
    ]
    assert importados == [date(2026, 10, 20), date(2026, 10, 21)]
    novo = partition_path(restaurada, date(2026, 10, 21)).read_bytes()
    assert novo == partition_path(origem, date(2026, 10, 21)).read_bytes()


def test_export_skips_published_assets(tmp_path):
    _bronze(tmp_path / "bronze", date(2026, 10, 20), date(2026, 10, 21))

    novos = exportar(tmp_path / "bronze", tmp_path / "out", {asset_name(date(2026, 10, 20))})

    assert [p.name for p in novos] == ["bronze_siac156_2026-10-21.parquet"]


def test_import_keeps_local_partitions_and_ignores_other_files(tmp_path):
    bronze, assets = tmp_path / "bronze", tmp_path / "assets"
    _bronze(bronze, date(2026, 10, 21))
    local = partition_path(bronze, date(2026, 10, 21)).read_bytes()
    assets.mkdir()
    (assets / asset_name(date(2026, 10, 21))).write_bytes(b"outro conteudo")
    (assets / "leiame.txt").write_text("x")

    assert importar(assets, bronze) == []
    assert partition_path(bronze, date(2026, 10, 21)).read_bytes() == local


def test_cli_historico(tmp_path):
    data_dir = tmp_path / "data"
    _bronze(data_dir / "bronze" / "siac156", date(2026, 10, 20), date(2026, 10, 21))
    publicados = tmp_path / "publicados.txt"
    publicados.write_text(asset_name(date(2026, 10, 20)) + "\n")
    runner, log = CliRunner(), ["--log-dir", str(tmp_path / "logs")]

    assets = str(tmp_path / "assets")
    exportar_args = [
        "exportar",
        assets,
        "--existentes",
        str(publicados),
        "--data-dir",
        str(data_dir),
    ]
    out = runner.invoke(app, [*log, "historico", *exportar_args])
    importar_args = ["importar", assets, "--data-dir", str(tmp_path / "novo")]
    restaurado = runner.invoke(app, [*log, "historico", *importar_args])

    assert out.exit_code == 0 and "1 asset(s) novo(s)" in out.stdout
    assert restaurado.exit_code == 0 and "1 partição(ões) importada(s)" in restaurado.stdout
