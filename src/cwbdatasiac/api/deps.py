from typing import Annotated

from fastapi import Depends, Request

from cwbdatasiac.api.db import Warehouse


def get_warehouse(request: Request) -> Warehouse:
    return request.app.state.warehouse


WarehouseDep = Annotated[Warehouse, Depends(get_warehouse)]

# Fato do último snapshot com as dimensões resolvidas; base das consultas por linha.
SOLICITACOES_FROM = """
    from marts.fct_solicitacoes as f
    join marts.dim_orgao as o using (orgao_sk)
    join marts.dim_assunto as a using (assunto_sk)
    join marts.dim_localidade as l using (localidade_sk)
    join marts.dim_origem as g using (origem_sk)
"""
