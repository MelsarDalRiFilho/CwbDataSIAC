import logging
import sys
from datetime import date

import httpx
import pytest
import respx

from cwbdatasiac import config
from cwbdatasiac.ingestion.discovery import (
    default_strategies,
    discover,
    from_browser,
    parse_manifest,
    parse_portal_table,
)
from cwbdatasiac.ingestion.errors import DiscoveryError
from tests.conftest import make_manifest, make_portal_payload

DICT = "2024-11-26_156_-_Dicionario_de_Dados.xlsx"
D19 = "2026-10-19_156_-_Base_de_Dados.csv"
D20 = "2026-10-20_156_-_Base_de_Dados.csv"


def test_parse_manifest_keeps_only_daily_csvs():
    files = parse_manifest(make_manifest(DICT, D19, D20))

    assert [f.name for f in files] == [D19, D20]
    assert files[1].url == config.MIRROR_BASE_URL + D20
    assert files[1].snapshot_date == date(2026, 10, 20)
    assert files[1].source == "manifesto"


@pytest.mark.parametrize("quote", ["'", '"'])
def test_parse_portal_table_accepts_both_quote_styles(quote):
    html = f"<a href={quote}https://mid-dadosabertos.curitiba.pr.gov.br/156/{D20}{quote}>x</a>"

    [file] = parse_portal_table(html)

    assert file.url.endswith(D20)
    assert file.snapshot_date == date(2026, 10, 20)


@pytest.fixture
def client():
    with httpx.Client() as c:
        yield c


STRATEGIES = default_strategies(use_browser=False)


@respx.mock
def test_discover_returns_latest_from_manifest(client):
    respx.get(config.MANIFEST_URL).respond(text=make_manifest(DICT, D19, D20))

    assert discover(client, strategies=STRATEGIES).name == D20


@respx.mock
def test_discover_returns_requested_date(client):
    respx.get(config.MANIFEST_URL).respond(text=make_manifest(D19, D20))

    assert discover(client, date(2026, 10, 19), strategies=STRATEGIES).name == D19


@respx.mock
def test_discover_falls_back_to_portal_and_logs(client, caplog):
    respx.get(config.MANIFEST_URL).respond(500)
    respx.get(config.PORTAL_FILES_URL).respond(text=make_portal_payload(D20, D19))

    with caplog.at_level(logging.WARNING):
        remote = discover(client, strategies=STRATEGIES)

    assert remote.source == "portal"
    assert remote.url == f"https://mid-dadosabertos.curitiba.pr.gov.br/156/{D20}"
    assert caplog.records[0].estrategia == "manifesto"


@respx.mock
def test_discover_falls_back_when_manifest_lacks_date(client):
    respx.get(config.MANIFEST_URL).respond(text=make_manifest(D19))
    respx.get(config.PORTAL_FILES_URL).respond(text=make_portal_payload(D20))

    assert discover(client, date(2026, 10, 20), strategies=STRATEGIES).source == "portal"


@respx.mock
def test_discover_raises_when_all_strategies_fail(client):
    respx.get(config.MANIFEST_URL).mock(side_effect=httpx.ConnectError("sem rede"))
    respx.get(config.PORTAL_FILES_URL).respond(text=make_portal_payload(sucesso=False))

    with pytest.raises(DiscoveryError, match="mais recente"):
        discover(client, strategies=STRATEGIES)


def test_default_strategies_include_browser_only_when_enabled():
    assert [n for n, _ in default_strategies(True)] == ["manifesto", "portal", "navegador"]
    assert [n for n, _ in default_strategies(False)] == ["manifesto", "portal"]


def test_browser_strategy_without_playwright(monkeypatch, client):
    monkeypatch.setitem(sys.modules, "playwright.sync_api", None)

    with pytest.raises(DiscoveryError, match="extra 'browser'"):
        from_browser(client)
