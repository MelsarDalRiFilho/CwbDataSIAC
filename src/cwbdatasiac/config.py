"""Configuração do pipeline: fontes, caminhos e limites das checagens."""

from dataclasses import dataclass
from pathlib import Path

DATASET_KEY = "0d5a7b06-3940-4be9-876e-bc8f23e96530"
DATASET_EXTENSION_KEY = "377f4e23-0e4f-4f11-954f-ae06ba689558"

MANIFEST_URL = "http://dadosabertos.c3sl.ufpr.br/curitiba/156/156.xml"
MIRROR_BASE_URL = "http://dadosabertos.c3sl.ufpr.br/curitiba/156/"
PORTAL_PAGE_URL = (
    f"https://dadosabertos.curitiba.pr.gov.br/conjuntodado/detalhe/?chave={DATASET_KEY}"
)
PORTAL_FILES_URL = "https://dadosabertos.curitiba.pr.gov.br/ConjuntoDado/DownloadArquivos/"

# Colunas nomeadas do CSV, na ordem do arquivo (a última coluna, vazia, é descartada).
EXPECTED_COLUMNS = (
    "Tipo",
    "Orgao",
    "DataCriacao",
    "Assunto",
    "Subdivisao",
    "Situacao",
    "Logradouro",
    "Bairro",
    "Regional",
    "DataResposta",
    "Origem",
)


@dataclass(frozen=True)
class IngestSettings:
    data_dir: Path = Path("data")
    min_bytes: int = 50_000_000
    keep_raw_days: int = 3
    use_browser: bool = True
    timeout_s: float = 120.0
    retry_attempts: int = 3
    retry_wait_s: float = 2.0
    # Fração máxima de linhas que podem violar regras bloqueantes do contrato.
    contract_tolerance: float = 0.001

    @property
    def raw_dir(self) -> Path:
        return self.data_dir / "raw"

    @property
    def bronze_dir(self) -> Path:
        return self.data_dir / "bronze" / "siac156"

    @property
    def quarantine_dir(self) -> Path:
        return self.data_dir / "quarentena"

    @property
    def quality_dir(self) -> Path:
        return self.data_dir / "qualidade"

    @property
    def warehouse_path(self) -> Path:
        return self.data_dir / "warehouse.duckdb"
