from datetime import date

import pytest

from cwbdatasiac.ingestion.checks import check_content, check_header, check_volume, read_header
from cwbdatasiac.ingestion.download import DownloadResult
from cwbdatasiac.ingestion.errors import CheckError
from tests.conftest import HEADER, make_csv


def _result(tmp_path, content: bytes, content_type: str = "text/csv; charset=utf-8"):
    path = tmp_path / "f.csv"
    path.write_bytes(content)
    return DownloadResult(path, len(content), "sha", content_type, 1)


@pytest.mark.parametrize("content_type", ["text/csv", "application/octet-stream", "TEXT/PLAIN"])
def test_check_content_accepts_known_types(tmp_path, content_type):
    check_content(_result(tmp_path, make_csv(), content_type), min_bytes=10)


def test_check_content_rejects_html(tmp_path):
    with pytest.raises(CheckError, match="Content-Type") as exc:
        check_content(_result(tmp_path, make_csv(), "text/html"), min_bytes=10)
    assert exc.value.etapa == "conteudo"
    assert exc.value.quarantine


def test_check_content_rejects_small_file(tmp_path):
    with pytest.raises(CheckError, match="abaixo do mínimo"):
        check_content(_result(tmp_path, make_csv()), min_bytes=10_000)


def test_check_content_requires_bom(tmp_path):
    with pytest.raises(CheckError, match="BOM"):
        check_content(_result(tmp_path, make_csv(bom=False)), min_bytes=10)


def test_read_header_drops_trailing_empty_column(tmp_path):
    path = tmp_path / "f.csv"
    path.write_bytes(make_csv())

    assert read_header(path)[0] == "Tipo"
    assert read_header(path)[-1] == "Origem"


def test_check_header_reports_missing_and_extra_columns(tmp_path):
    path = tmp_path / "f.csv"
    path.write_bytes(make_csv(header=HEADER.replace("Bairro;", "Protocolo;")))

    with pytest.raises(
        CheckError, match=r"faltando: \['Bairro'\]; colunas inesperadas: \['Protocolo'\]"
    ):
        check_header(path)


def test_check_volume_rejects_shrinking_file_in_same_year():
    with pytest.raises(CheckError, match="menos que as 100"):
        check_volume(99, date(2026, 10, 20), (date(2026, 10, 19), 100))


def test_check_volume_allows_shrink_on_year_turn():
    check_volume(10, date(2027, 1, 1), (date(2026, 12, 31), 900_000))


def test_check_volume_rejects_empty_file():
    with pytest.raises(CheckError, match="sem linhas"):
        check_volume(0, date(2026, 10, 20), None)
