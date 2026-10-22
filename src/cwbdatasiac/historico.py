"""Histórico durável da Bronze como arquivos soltos (assets da release `dados` no GitHub).

Cada partição `bronze/siac156/snapshot_data=AAAA-MM-DD/part-0.parquet` vira um asset
`bronze_siac156_AAAA-MM-DD.parquet`. O workflow diário baixa os assets, importa para a
Bronze, roda o pipeline e envia só as partições novas. O warehouse é derivado: o dbt o
reconstrói a partir da Bronze se o cache do Actions não existir.
"""

import re
import shutil
from datetime import date
from pathlib import Path

from cwbdatasiac.ingestion.bronze import partition_path

ASSET_RE = re.compile(r"^bronze_siac156_(\d{4}-\d{2}-\d{2})\.parquet$")
PARTITION_RE = re.compile(r"^snapshot_data=(\d{4}-\d{2}-\d{2})$")


def asset_name(snapshot_date: date) -> str:
    return f"bronze_siac156_{snapshot_date.isoformat()}.parquet"


def importar(origem: Path, bronze_dir: Path) -> list[date]:
    """Copia os assets de `origem` para as partições da Bronze que ainda não existem."""
    importados = []
    for asset in sorted(origem.glob("*.parquet")):
        if not (match := ASSET_RE.match(asset.name)):
            continue
        snapshot = date.fromisoformat(match.group(1))
        destino = partition_path(bronze_dir, snapshot)
        if destino.exists():
            continue
        destino.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(asset, destino)
        importados.append(snapshot)
    return importados


def exportar(bronze_dir: Path, destino: Path, existentes: set[str]) -> list[Path]:
    """Copia para `destino` as partições cujo asset ainda não está em `existentes`."""
    destino.mkdir(parents=True, exist_ok=True)
    exportados = []
    for particao in sorted(bronze_dir.glob("snapshot_data=*")):
        match = PARTITION_RE.match(particao.name)
        arquivo = particao / "part-0.parquet"
        if not match or not arquivo.exists():
            continue
        nome = asset_name(date.fromisoformat(match.group(1)))
        if nome in existentes:
            continue
        shutil.copy2(arquivo, destino / nome)
        exportados.append(destino / nome)
    return exportados
