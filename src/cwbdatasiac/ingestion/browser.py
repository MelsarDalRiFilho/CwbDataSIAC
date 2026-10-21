"""Descoberta pelo navegador: abre o portal, clica em DOWNLOAD e lê a tabela do modal.

Último recurso, para quando o endpoint JSON do portal mudar. Requer o extra `browser`:

    uv sync --extra browser && uv run playwright install chromium
"""

from cwbdatasiac import config
from cwbdatasiac.ingestion.discovery import RemoteFile, parse_portal_table
from cwbdatasiac.ingestion.errors import DiscoveryError


def list_files_with_browser(timeout_ms: int = 60_000) -> list[RemoteFile]:
    try:
        from playwright.sync_api import sync_playwright
    except ImportError as exc:
        raise DiscoveryError("extra 'browser' não instalado (playwright ausente)") from exc

    with sync_playwright() as p:  # pragma: no cover - exige navegador instalado
        browser = p.chromium.launch(headless=True)
        try:
            page = browser.new_page()
            page.goto(config.PORTAL_PAGE_URL, timeout=timeout_ms)
            # Um tutorial guiado cobre a página na primeira visita e intercepta os cliques.
            close_tutorial = page.locator("#tutorial .closeTut:visible").first
            if close_tutorial.count():
                close_tutorial.click(timeout=timeout_ms)
            # O botão DOWNLOAD fica na aba "Dados", que não é a aba aberta por padrão.
            page.click("#acesso-tab", timeout=timeout_ms)
            page.click(
                f"[onclick*=\"downloadArquivos('{config.DATASET_KEY}'\"]", timeout=timeout_ms
            )
            table = page.locator("#tabelaDownloadArquivos")
            table.locator("a[href$='.csv']").first.wait_for(timeout=timeout_ms)
            return parse_portal_table(table.inner_html(), source="navegador")
        finally:
            browser.close()
