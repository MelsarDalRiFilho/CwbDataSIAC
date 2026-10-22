"""Gera o site estático publicado no GitHub Pages.

    site/
      index.html, css/, js/, geo/   ← dashboard/ (o mesmo servido pela API em /painel)
      data/<chave>.json             ← respostas da API, só agregados
      data/manifest.json            ← marca o modo estático para o dashboard
      relatorio/index.html          ← relatório analítico
      dbt/index.html                ← documentação e linhagem do dbt (se gerada)

Os JSON são obtidos chamando a própria API em processo (TestClient), então têm
exatamente o formato que o dashboard recebe no modo local. `/solicitacoes` (linha
a linha) não é exportado: o Pages recebe só agregados.
"""

import json
import logging
import shutil
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from fastapi.testclient import TestClient

from cwbdatasiac import __version__
from cwbdatasiac.api.main import create_app
from cwbdatasiac.config import REPO_ROOT
from cwbdatasiac.report import render_report

DASHBOARD_DIR = REPO_ROOT / "dashboard"
DBT_DOCS = REPO_ROOT / "dbt" / "siac156" / "target" / "static_index.html"

# Chave → rota da API. O dashboard (dashboard/js/app.js, objeto SOURCES) usa as mesmas
# chaves: na API chama a rota; no Pages lê data/<chave>.json. Um teste garante a paridade.
SOURCES = {
    "health": "/health",
    "qualidade": "/qualidade",
    "resumo": "/indicadores/resumo",
    "serie_dia": "/indicadores/serie-temporal?granularidade=dia",
    "serie_semana": "/indicadores/serie-temporal?granularidade=semana",
    "serie_mes": "/indicadores/serie-temporal?granularidade=mes",
    "por_orgao": "/indicadores/por-orgao?limite=200",
    "por_origem": "/indicadores/por-origem",
    "por_assunto": "/indicadores/por-assunto?limite=200",
    "por_bairro": "/indicadores/por-bairro?limite=200",
    "tempo_resposta": "/indicadores/tempo-resposta",
    "historico": "/indicadores/historico-situacao",
    "calor": "/indicadores/dia-semana-mes",
}

log = logging.getLogger(__name__)


class ExportError(Exception):
    pass


def collect(data_dir: Path) -> dict[str, Any]:
    """Respostas da API para cada chave de SOURCES."""
    client = TestClient(create_app(data_dir))
    data = {}
    for key, route in SOURCES.items():
        response = client.get(route)
        if response.status_code != 200:
            raise ExportError(f"{route} respondeu {response.status_code}: {response.text[:200]}")
        data[key] = response.json()
    return data


def build_site(data_dir: Path, out_dir: Path) -> Path:
    data = collect(data_dir)
    if out_dir.exists():
        shutil.rmtree(out_dir)
    shutil.copytree(DASHBOARD_DIR, out_dir)

    data_out = out_dir / "data"
    data_out.mkdir()
    for key, payload in data.items():
        (data_out / f"{key}.json").write_text(
            json.dumps(payload, ensure_ascii=False), encoding="utf-8"
        )
    manifest = {
        "gerado_em": datetime.now(UTC).isoformat(timespec="seconds"),
        "versao": __version__,
        "snapshot_data": data["resumo"]["snapshot_data"],
        "arquivos": sorted(f"{key}.json" for key in data),
    }
    (data_out / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False), "utf-8")

    report_dir = out_dir / "relatorio"
    report_dir.mkdir()
    (report_dir / "index.html").write_text(render_report(data), encoding="utf-8")

    if DBT_DOCS.exists():
        (out_dir / "dbt").mkdir()
        shutil.copy(DBT_DOCS, out_dir / "dbt" / "index.html")
    else:
        log.warning("documentação do dbt ausente; rode `cwbdatasiac docs` antes", extra={})

    log.info(
        "site gerado",
        extra={"etapa": "site", "destino": str(out_dir), "snapshot": manifest["snapshot_data"]},
    )
    return out_dir
