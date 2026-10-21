"""Descobre a URL do snapshot diário, tentando três estratégias em ordem:

1. manifesto `156.xml` do espelho C3SL (UFPR);
2. endpoint JSON que alimenta o botão DOWNLOAD do portal oficial;
3. navegador headless (Playwright), opcional, se o JSON do portal mudar.
"""

import logging
import re
import xml.etree.ElementTree as ET
from collections.abc import Callable
from dataclasses import dataclass
from datetime import date
from urllib.parse import urljoin

import httpx

from cwbdatasiac import config
from cwbdatasiac.ingestion.errors import DiscoveryError

log = logging.getLogger(__name__)

FILE_NAME_RE = re.compile(r"^(\d{4}-\d{2}-\d{2})_156_-_Base_de_Dados\.csv$")
PORTAL_HREF_RE = re.compile(
    r"""href=["'](https?://[^"']+/(\d{4}-\d{2}-\d{2}_156_-_Base_de_Dados\.csv))["']"""
)


@dataclass(frozen=True)
class RemoteFile:
    name: str
    url: str
    snapshot_date: date
    source: str


def _snapshot_date(name: str) -> date | None:
    match = FILE_NAME_RE.match(name)
    return date.fromisoformat(match.group(1)) if match else None


def parse_manifest(xml_text: str, base_url: str = config.MIRROR_BASE_URL) -> list[RemoteFile]:
    files = []
    for node in ET.fromstring(xml_text).iter("dado"):
        name = node.get("arquivo", "")
        if snapshot := _snapshot_date(name):
            files.append(RemoteFile(name, urljoin(base_url, name), snapshot, "manifesto"))
    return files


def parse_portal_table(html: str, source: str = "portal") -> list[RemoteFile]:
    return [
        RemoteFile(name, url, snapshot, source)
        for url, name in PORTAL_HREF_RE.findall(html)
        if (snapshot := _snapshot_date(name))
    ]


def from_manifest(client: httpx.Client) -> list[RemoteFile]:
    response = client.get(config.MANIFEST_URL)
    response.raise_for_status()
    return parse_manifest(response.text)


def from_portal(client: httpx.Client) -> list[RemoteFile]:
    """Só a primeira página (50 arquivos mais recentes): suficiente para a carga diária."""
    response = client.get(
        config.PORTAL_FILES_URL,
        params={
            "conjuntoDadoChave": config.DATASET_KEY,
            "conjuntoDadoExtensao": config.DATASET_EXTENSION_KEY,
            "pagina": 1,
            "tamanhoPagina": 50,
        },
    )
    response.raise_for_status()
    payload = response.json()
    if not payload.get("sucesso"):
        raise DiscoveryError(f"portal respondeu sem sucesso: {payload.get('erro')!r}")
    return parse_portal_table(payload["tabela"])


def from_browser(client: httpx.Client) -> list[RemoteFile]:
    from cwbdatasiac.ingestion.browser import list_files_with_browser

    return list_files_with_browser()


Strategy = Callable[[httpx.Client], list[RemoteFile]]


def default_strategies(use_browser: bool) -> list[tuple[str, Strategy]]:
    strategies: list[tuple[str, Strategy]] = [("manifesto", from_manifest), ("portal", from_portal)]
    if use_browser:
        strategies.append(("navegador", from_browser))
    return strategies


def discover(
    client: httpx.Client,
    snapshot_date: date | None = None,
    strategies: list[tuple[str, Strategy]] | None = None,
) -> RemoteFile:
    """Retorna o snapshot pedido (ou o mais recente) da primeira estratégia que o encontrar."""
    for name, strategy in strategies or default_strategies(use_browser=True):
        try:
            files = strategy(client)
        except Exception as exc:
            log.warning(
                "estratégia de descoberta falhou",
                extra={"etapa": "descoberta", "estrategia": name, "erro": repr(exc)},
            )
            continue

        candidates = [f for f in files if snapshot_date in (None, f.snapshot_date)]
        if candidates:
            chosen = max(candidates, key=lambda f: f.snapshot_date)
            log.info(
                "arquivo descoberto",
                extra={"etapa": "descoberta", "estrategia": name, "arquivo": chosen.name},
            )
            return chosen
        log.warning(
            "estratégia não encontrou o snapshot",
            extra={"etapa": "descoberta", "estrategia": name, "arquivos": len(files)},
        )

    wanted = snapshot_date.isoformat() if snapshot_date else "mais recente"
    raise DiscoveryError(f"nenhuma estratégia encontrou o snapshot ({wanted})")
