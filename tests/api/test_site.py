"""Site estático, relatório e painel sobre o warehouse sintético (fixture de sessão)."""

import json
import re

import pytest
from fastapi.testclient import TestClient
from typer.testing import CliRunner

from cwbdatasiac import site
from cwbdatasiac.api.main import create_app
from cwbdatasiac.cli import app
from cwbdatasiac.report import achados

pytestmark = pytest.mark.slow


def test_dashboard_sources_match_python_exports():
    js = (site.DASHBOARD_DIR / "js" / "app.js").read_text(encoding="utf-8")
    block = re.search(r"const SOURCES = \{(.*?)\};", js, re.S).group(1)

    assert dict(re.findall(r'(\w+): "([^"]+)"', block)) == site.SOURCES


@pytest.fixture(scope="module")
def built(warehouse_dir, tmp_path_factory):
    return site.build_site(warehouse_dir, tmp_path_factory.mktemp("site") / "site")


def test_site_has_dashboard_data_and_report(built):
    assert (built / "index.html").exists()
    assert (built / "geo" / "bairros.geojson").exists()
    manifest = json.loads((built / "data" / "manifest.json").read_text())
    assert manifest["snapshot_data"] == "2026-10-21"
    assert sorted(p.stem for p in (built / "data").glob("*.json")) == sorted(
        [*site.SOURCES, "manifest"]
    )
    resumo = json.loads((built / "data" / "resumo.json").read_text())
    assert resumo["solicitacoes"] == 5
    report = (built / "relatorio" / "index.html").read_text()
    assert "Volume e canais de entrada" in report
    assert "5 solicitações" in report


def test_site_publishes_only_aggregates(built):
    published = " ".join(p.read_text(encoding="utf-8") for p in built.rglob("*.json"))
    published += (built / "relatorio" / "index.html").read_text(encoding="utf-8")

    assert not (built / "data" / "solicitacoes.json").exists()
    assert "Rua Exemplo" not in published
    assert "logradouro" not in published.lower()


def test_build_site_replaces_previous_output(warehouse_dir, tmp_path):
    out = tmp_path / "site"
    out.mkdir()
    (out / "velho.txt").write_text("x")

    site.build_site(warehouse_dir, out)

    assert not (out / "velho.txt").exists()


def test_collect_fails_loudly_without_warehouse(tmp_path):
    with pytest.raises(site.ExportError, match="503"):
        site.collect(tmp_path)


def test_findings_on_small_dataset(warehouse_dir):
    textos = {a.titulo: a.texto for a in achados(site.collect(warehouse_dir))}

    assert textos["Volume e canais de entrada"].startswith("Até 21/10/2026")
    # Nenhum órgão sintético tem 1.000 solicitações: o ranking usa todos e diz isso.
    assert textos["Onde está o gargalo"].startswith(
        "Entre todos os órgãos, Secretaria Municipal do Meio Ambiente tem a menor taxa"
    )
    assert textos["Bairros com mais demandas"].startswith("Xaxim e Centro concentram")
    assert "sem violações" not in textos["Sobre os dados"]  # há uma violação de alerta


def test_api_serves_dashboard(warehouse_dir):
    client = TestClient(create_app(warehouse_dir))

    assert client.get("/", follow_redirects=False).headers["location"] == "/painel/"
    page = client.get("/painel/")
    assert page.status_code == 200
    assert "SIAC 156" in page.text
    assert client.get("/painel/js/app.js").status_code == 200


def test_cli_report_and_site(warehouse_dir, tmp_path):
    runner = CliRunner()
    log = ["--log-dir", str(tmp_path / "logs")]
    data = ["--data-dir", str(warehouse_dir)]

    report = runner.invoke(app, [*log, "report", *data, "--saida", str(tmp_path / "r.html")])
    built = runner.invoke(app, [*log, "site", *data, "--saida", str(tmp_path / "s")])

    assert report.exit_code == 0, report.output
    assert "Sazonalidade" in (tmp_path / "r.html").read_text()
    assert built.exit_code == 0, built.output
    assert (tmp_path / "s" / "data" / "manifest.json").exists()
