import hashlib
from datetime import date

import httpx
import pytest
import respx

from cwbdatasiac.ingestion.discovery import RemoteFile
from cwbdatasiac.ingestion.download import download
from cwbdatasiac.ingestion.errors import DownloadError

URL = "http://example.test/2026-10-20_156_-_Base_de_Dados.csv"
REMOTE = RemoteFile("2026-10-20_156_-_Base_de_Dados.csv", URL, date(2026, 10, 20), "manifesto")


@pytest.fixture
def client():
    with httpx.Client() as c:
        yield c


@respx.mock
def test_download_writes_file_and_sha256(client, tmp_path):
    respx.get(URL).respond(content=b"abc", headers={"content-type": "text/csv"})

    result = download(client, REMOTE, tmp_path, wait_s=0)

    assert result.path.read_bytes() == b"abc"
    assert result.bytes == 3
    assert result.sha256 == hashlib.sha256(b"abc").hexdigest()
    assert result.content_type == "text/csv"
    assert result.attempts == 1


@respx.mock
def test_download_retries_server_errors(client, tmp_path):
    route = respx.get(URL)
    route.side_effect = [httpx.Response(503), httpx.Response(200, content=b"ok")]

    result = download(client, REMOTE, tmp_path, wait_s=0)

    assert result.attempts == 2
    assert route.call_count == 2


@respx.mock
def test_download_does_not_retry_not_found(client, tmp_path):
    route = respx.get(URL).respond(404)

    with pytest.raises(DownloadError, match="404"):
        download(client, REMOTE, tmp_path, wait_s=0)
    assert route.call_count == 1


@respx.mock
def test_download_gives_up_after_attempts_and_cleans_partial_file(client, tmp_path):
    route = respx.get(URL).mock(side_effect=httpx.ReadTimeout("lento"))

    with pytest.raises(DownloadError, match="3 tentativas"):
        download(client, REMOTE, tmp_path, attempts=3, wait_s=0)
    assert route.call_count == 3
    assert list(tmp_path.iterdir()) == []
