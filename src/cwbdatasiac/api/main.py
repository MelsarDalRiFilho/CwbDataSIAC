"""Aplicação FastAPI: serve a camada Gold do warehouse em modo somente leitura.

uv run cwbdatasiac api          # ou: uv run uvicorn cwbdatasiac.api.main:app
"""

import os
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles

from cwbdatasiac import __version__
from cwbdatasiac.api.db import Warehouse, WarehouseUnavailable
from cwbdatasiac.api.routers import indicadores, operacao, solicitacoes
from cwbdatasiac.config import REPO_ROOT

DATA_DIR_ENV = "CWBDATASIAC_DATA_DIR"
RETRY_AFTER_S = 10
DASHBOARD_DIR = REPO_ROOT / "dashboard"

DESCRIPTION = """
Indicadores e solicitações do **SIAC 156** de Curitiba (dados abertos da Prefeitura, CC BY 4.0).

- Tudo vem do **último snapshot** diário carregado; não há número de protocolo e linhas iguais
  são solicitações distintas (ADR 0001).
- Endereços (`Logradouro`) não são expostos: o menor nível geográfico é o bairro.
- Durante a atualização do pipeline (poucos segundos), as rotas respondem **503** com `Retry-After`.
- O painel em ECharts está em [/painel/](/painel/).
"""


def create_app(data_dir: Path | None = None) -> FastAPI:
    data_dir = data_dir or Path(os.environ.get(DATA_DIR_ENV, "data"))
    app = FastAPI(title="CwbDataSIAC — SIAC 156", version=__version__, description=DESCRIPTION)
    app.state.warehouse = Warehouse(data_dir / "warehouse.duckdb")

    @app.exception_handler(WarehouseUnavailable)
    def _unavailable(request: Request, exc: WarehouseUnavailable) -> JSONResponse:
        return JSONResponse(
            status_code=503,
            content={"detail": "warehouse indisponível (pipeline em execução ou sem dados)"},
            headers={"Retry-After": str(RETRY_AFTER_S)},
        )

    app.include_router(operacao.router)
    app.include_router(solicitacoes.router)
    app.include_router(indicadores.router)

    # O mesmo painel publicado no Pages, lendo a API em vez dos JSON estáticos.
    app.mount("/painel", StaticFiles(directory=DASHBOARD_DIR, html=True), name="painel")

    @app.get("/", include_in_schema=False)
    def _root() -> RedirectResponse:
        return RedirectResponse("/painel/")

    return app


app = create_app()
