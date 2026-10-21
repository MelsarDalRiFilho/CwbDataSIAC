"""Download em streaming com retry, sha256 e escrita atômica (arquivo .part + rename)."""

import hashlib
import logging
from dataclasses import dataclass
from pathlib import Path

import httpx
from tenacity import (
    RetryError,
    Retrying,
    retry_if_exception,
    stop_after_attempt,
    wait_exponential,
)

from cwbdatasiac.ingestion.discovery import RemoteFile
from cwbdatasiac.ingestion.errors import DownloadError

log = logging.getLogger(__name__)

CHUNK_SIZE = 1024 * 1024


@dataclass(frozen=True)
class DownloadResult:
    path: Path
    bytes: int
    sha256: str
    content_type: str
    attempts: int


def _is_retryable(exc: BaseException) -> bool:
    if isinstance(exc, httpx.HTTPStatusError):
        return exc.response.status_code >= 500 or exc.response.status_code == 429
    return isinstance(exc, httpx.TransportError)


def _fetch(client: httpx.Client, remote: RemoteFile, dest: Path) -> tuple[int, str, str]:
    part = dest.with_name(dest.name + ".part")
    digest = hashlib.sha256()
    size = 0
    try:
        with client.stream("GET", remote.url) as response:
            response.raise_for_status()
            with part.open("wb") as fh:
                for chunk in response.iter_bytes(CHUNK_SIZE):
                    fh.write(chunk)
                    digest.update(chunk)
                    size += len(chunk)
            content_type = response.headers.get("content-type", "")
    except BaseException:
        part.unlink(missing_ok=True)
        raise
    part.replace(dest)
    return size, digest.hexdigest(), content_type


def download(
    client: httpx.Client,
    remote: RemoteFile,
    dest_dir: Path,
    *,
    attempts: int = 3,
    wait_s: float = 2.0,
) -> DownloadResult:
    dest_dir.mkdir(parents=True, exist_ok=True)
    dest = dest_dir / remote.name
    retrying = Retrying(
        stop=stop_after_attempt(attempts),
        wait=wait_exponential(multiplier=wait_s, max=60),
        retry=retry_if_exception(_is_retryable),
        before_sleep=lambda state: log.warning(
            "nova tentativa de download",
            extra={
                "etapa": "download",
                "tentativa": state.attempt_number,
                "erro": repr(state.outcome.exception()),
            },
        ),
    )
    try:
        size, sha256, content_type = retrying(_fetch, client, remote, dest)
    except RetryError as exc:
        cause = exc.last_attempt.exception()
        raise DownloadError(f"download falhou após {attempts} tentativas: {cause!r}") from cause
    except httpx.HTTPError as exc:
        raise DownloadError(f"download falhou: {exc!r}") from exc

    result = DownloadResult(dest, size, sha256, content_type, retrying.statistics["attempt_number"])
    log.info(
        "download concluído",
        extra={
            "etapa": "download",
            "url": remote.url,
            "bytes": size,
            "sha256": sha256,
            "tentativas": result.attempts,
        },
    )
    return result
