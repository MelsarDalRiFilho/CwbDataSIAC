"""Saúde da API, histórico de ingestões e qualidade da última carga."""

from typing import Annotated

from fastapi import APIRouter, Query

from cwbdatasiac.api.db import WarehouseUnavailable
from cwbdatasiac.api.deps import WarehouseDep
from cwbdatasiac.api.schemas import Health, Ingestao, Qualidade, Violacao

router = APIRouter(tags=["operação"])

INGESTAO_COLUMNS = """run_id, snapshot_data, arquivo, fonte_descoberta, inicio, fim, status,
    etapa_falha, mensagem, bytes, linhas"""


@router.get("/health", response_model=Health)
def health(warehouse: WarehouseDep) -> Health:
    """Sempre 200: informa se o warehouse está acessível e qual o snapshot servido."""
    try:
        row = warehouse.query_one("select max(snapshot_data) as s from marts.fct_solicitacoes")
    except WarehouseUnavailable:
        return Health(status="indisponivel")
    return Health(status="ok", ultimo_snapshot=row["s"] if row else None)


@router.get("/ingestoes", response_model=list[Ingestao])
def ingestoes(
    warehouse: WarehouseDep,
    status: Annotated[str | None, Query(description="sucesso, sem_novidade ou falha")] = None,
    limite: Annotated[int, Query(ge=1, le=500)] = 30,
) -> list[dict]:
    """Execuções da ingestão, da mais recente para a mais antiga."""
    return warehouse.query(
        f"""select {INGESTAO_COLUMNS} from controle.ingestao_execucoes
            where ? is null or status = ? order by inicio desc limit ?""",
        [status, status, limite],
    )


@router.get("/qualidade", response_model=Qualidade)
def qualidade(warehouse: WarehouseDep) -> Qualidade:
    """Última ingestão, última carga bem-sucedida e as violações de contrato dessa carga."""
    ultima = warehouse.query_one(
        f"select {INGESTAO_COLUMNS} from controle.ingestao_execucoes order by inicio desc limit 1"
    )
    carga = warehouse.query_one(
        f"""select {INGESTAO_COLUMNS} from controle.ingestao_execucoes
            where status = 'sucesso' order by inicio desc limit 1"""
    )
    violacoes = []
    if carga:
        violacoes = warehouse.query(
            """select regra, coluna, severidade, linhas, exemplos
               from controle.contrato_violacoes where run_id = ?
               order by severidade, linhas desc""",
            [carga["run_id"]],
        )
    return Qualidade(
        ultima_ingestao=ultima,
        ultima_carga=carga,
        violacoes=[Violacao(**v) for v in violacoes],
    )
