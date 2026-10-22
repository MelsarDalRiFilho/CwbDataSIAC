"""Aplicação FastAPI: serve a camada Gold do warehouse em modo somente leitura.

uv run cwbdatasiac api          # ou: uv run uvicorn cwbdatasiac.api.main:app
"""

import os
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from cwbdatasiac import __version__
from cwbdatasiac.api.db import Warehouse, WarehouseUnavailable
from cwbdatasiac.api.routers import indicadores, operacao, solicitacoes

DATA_DIR_ENV = "CWBDATASIAC_DATA_DIR"
RETRY_AFTER_S = 10

DESCRIPTION = """
Indicadores e solicitações do **SIAC 156** de Curitiba (dados abertos da Prefeitura, CC BY 4.0).

- Tudo vem do **último snapshot** diário carregado; não há número de protocolo e linhas iguais
  são solicitações distintas (ADR 0001).
- Endereços (`Logradouro`) não são expostos: o menor nível geográfico é o bairro.
- Durante a atualização do pipeline (poucos segundos), as rotas respondem **503** com `Retry-After`.
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
    return app


app = create_app()
