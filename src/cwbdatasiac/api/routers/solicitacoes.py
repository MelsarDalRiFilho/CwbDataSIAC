"""Solicitações do último snapshot, com filtros e paginação. Nunca expõe logradouro."""

from datetime import date
from typing import Annotated, Any

from fastapi import APIRouter, Query

from cwbdatasiac.api.deps import SOLICITACOES_FROM, WarehouseDep
from cwbdatasiac.api.schemas import PaginaSolicitacoes

router = APIRouter(tags=["solicitações"])

# Filtro de igualdade exposto na API → coluna SQL. Lista fechada: nada do usuário vira SQL.
EQUALITY_FILTERS = {
    "orgao": "o.orgao",
    "assunto": "a.assunto",
    "bairro": "l.bairro",
    "regional": "l.regional",
    "origem": "g.origem",
    "tipo": "f.tipo",
    "situacao": "f.situacao",
}


@router.get("/solicitacoes", response_model=PaginaSolicitacoes)
def solicitacoes(
    warehouse: WarehouseDep,
    data_inicio: Annotated[date | None, Query(description="Criadas a partir de")] = None,
    data_fim: Annotated[date | None, Query(description="Criadas até")] = None,
    orgao: str | None = None,
    assunto: str | None = None,
    bairro: str | None = None,
    regional: str | None = None,
    origem: str | None = None,
    tipo: str | None = None,
    situacao: str | None = None,
    respondida: bool | None = None,
    pagina: Annotated[int, Query(ge=1)] = 1,
    tamanho: Annotated[int, Query(ge=1, le=500)] = 50,
) -> dict[str, Any]:
    """Linhas do retrato atual, das mais recentes para as mais antigas."""
    equality = {
        "orgao": orgao,
        "assunto": assunto,
        "bairro": bairro,
        "regional": regional,
        "origem": origem,
        "tipo": tipo,
        "situacao": situacao,
    }
    where, params = ["true"], []
    for name, value in equality.items():
        if value is not None:
            where.append(f"{EQUALITY_FILTERS[name]} = ?")
            params.append(value)
    if data_inicio:
        where.append("f.data_criacao >= ?")
        params.append(data_inicio)
    if data_fim:
        where.append("f.data_criacao <= ?")
        params.append(data_fim)
    if respondida is not None:
        where.append("f.respondida = ?")
        params.append(respondida)
    condition = " and ".join(where)

    header = warehouse.query_one(
        f"select count(*) as total, max(f.snapshot_data) as snapshot_data "
        f"{SOLICITACOES_FROM} where {condition}",
        params,
    )
    itens = warehouse.query(
        f"""select f.solicitacao_sk, f.data_criacao, f.data_resposta, f.tipo, f.situacao,
                   o.orgao, a.assunto, a.subdivisao, l.bairro, l.regional, g.origem,
                   f.respondida, f.dias_ate_resposta, f.dias_em_aberto
            {SOLICITACOES_FROM}
            where {condition}
            order by f.data_criacao desc, f.linha
            limit ? offset ?""",
        [*params, tamanho, (pagina - 1) * tamanho],
    )
    return {
        "snapshot_data": header["snapshot_data"] if header else None,
        "total": header["total"] if header else 0,
        "pagina": pagina,
        "tamanho": tamanho,
        "itens": itens,
    }
