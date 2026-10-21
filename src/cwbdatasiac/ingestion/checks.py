"""Checagens pós-captura: confirmam que o serviço entregou um arquivo utilizável.

Cada checagem levanta `CheckError` com a etapa e o motivo; o pipeline registra a
falha, envia o arquivo para a quarentena e encerra com exit code ≠ 0.
"""

from datetime import date
from pathlib import Path

from cwbdatasiac.config import EXPECTED_COLUMNS
from cwbdatasiac.ingestion.download import DownloadResult
from cwbdatasiac.ingestion.errors import CheckError

UTF8_BOM = b"\xef\xbb\xbf"
# O espelho C3SL responde text/csv; o host oficial, application/octet-stream.
ACCEPTED_CONTENT_TYPES = ("text/csv", "text/plain", "application/octet-stream")


def check_content(result: DownloadResult, min_bytes: int) -> None:
    media_type = result.content_type.split(";")[0].strip().lower()
    if media_type not in ACCEPTED_CONTENT_TYPES:
        raise CheckError("conteudo", f"Content-Type inesperado: {result.content_type!r}")
    if result.bytes < min_bytes:
        raise CheckError(
            "conteudo", f"arquivo com {result.bytes} bytes, abaixo do mínimo de {min_bytes}"
        )
    with result.path.open("rb") as fh:
        if fh.read(len(UTF8_BOM)) != UTF8_BOM:
            raise CheckError("conteudo", "arquivo sem BOM UTF-8; encoding pode ter mudado")


def read_header(path: Path) -> list[str]:
    with path.open(encoding="utf-8-sig", newline="") as fh:
        line = fh.readline().rstrip("\r\n")
    columns = line.split(";")
    # O arquivo termina cada linha com ';', o que gera uma coluna final vazia.
    if columns and columns[-1] == "":
        columns.pop()
    return columns


def check_header(path: Path) -> None:
    columns = read_header(path)
    missing = [c for c in EXPECTED_COLUMNS if c not in columns]
    extra = [c for c in columns if c not in EXPECTED_COLUMNS]
    if missing or extra:
        raise CheckError("cabecalho", f"colunas faltando: {missing}; colunas inesperadas: {extra}")


def check_volume(rows: int, snapshot_date: date, previous: tuple[date, int] | None) -> None:
    """O arquivo acumula o ano: não pode encolher, exceto na virada do ano."""
    if rows == 0:
        raise CheckError("volume", "arquivo sem linhas de dados")
    if previous is None:
        return
    previous_date, previous_rows = previous
    if previous_date.year == snapshot_date.year and rows < previous_rows:
        raise CheckError(
            "volume",
            f"{rows} linhas, menos que as {previous_rows} do snapshot de {previous_date}",
        )
