"""Indicadores agregados para o dashboard e o relatório."""

from datetime import date
from typing import Annotated

from fastapi import APIRouter, Query

from cwbdatasiac.api.deps import SOLICITACOES_FROM, WarehouseDep
from cwbdatasiac.api.schemas import (
    DiaSemanaMes,
    Granularidade,
    PontoSerie,
    PorAssunto,
    PorBairro,
    PorOrgao,
    PorOrigem,
    Resumo,
    SituacaoNoSnapshot,
    TempoResposta,
)

router = APIRouter(prefix="/indicadores", tags=["indicadores"])

TRUNC_UNIT = {Granularidade.dia: "day", Granularidade.semana: "week", Granularidade.mes: "month"}

Limite = Annotated[int, Query(ge=1, le=200)]


@router.get("/resumo", response_model=Resumo)
def resumo(warehouse: WarehouseDep) -> dict:
    """KPIs do último snapshot."""
    return warehouse.query_one(
        """select max(snapshot_data) as snapshot_data,
                  count(*) as solicitacoes,
                  count(*) filter (where respondida) as respondidas,
                  count(*) filter (where not respondida) as pendentes,
                  round(count(*) filter (where respondida) / nullif(count(*), 0), 4)
                      as taxa_resposta,
                  median(dias_ate_resposta) as mediana_dias_resposta,
                  median(dias_em_aberto) as mediana_dias_em_aberto
           from marts.fct_solicitacoes"""
    )


@router.get("/serie-temporal", response_model=list[PontoSerie])
def serie_temporal(
    warehouse: WarehouseDep,
    granularidade: Granularidade = Granularidade.dia,
    data_inicio: date | None = None,
    data_fim: date | None = None,
) -> list[dict]:
    """Solicitações criadas e respondidas por período (semana começa na segunda)."""
    unit = TRUNC_UNIT[granularidade]
    return warehouse.query(
        f"""select date_trunc('{unit}', data)::date as periodo,
                   sum(criadas)::bigint as criadas, sum(respondidas)::bigint as respondidas
            from marts.agg_diario
            where (? is null or data >= ?) and (? is null or data <= ?)
            group by 1 order by 1""",
        [data_inicio, data_inicio, data_fim, data_fim],
    )


@router.get("/por-orgao", response_model=list[PorOrgao])
def por_orgao(warehouse: WarehouseDep, limite: Limite = 50) -> list[dict]:
    return warehouse.query(
        f"""select o.orgao, count(*) as solicitacoes,
                   count(*) filter (where not f.respondida) as pendentes
            {SOLICITACOES_FROM}
            group by 1 order by solicitacoes desc, o.orgao limit ?""",
        [limite],
    )


@router.get("/por-origem", response_model=list[PorOrigem])
def por_origem(warehouse: WarehouseDep) -> list[dict]:
    """Canal de entrada das solicitações."""
    return warehouse.query(
        f"""select g.origem, count(*) as solicitacoes
            {SOLICITACOES_FROM}
            group by 1 order by solicitacoes desc, g.origem"""
    )


@router.get("/por-assunto", response_model=list[PorAssunto])
def por_assunto(
    warehouse: WarehouseDep, orgao: str | None = None, limite: Limite = 15
) -> list[dict]:
    """Assuntos mais frequentes (por órgão), base do treemap órgão → assunto."""
    return warehouse.query(
        f"""select o.orgao, a.assunto, count(*) as solicitacoes
            {SOLICITACOES_FROM}
            where ? is null or o.orgao = ?
            group by 1, 2 order by solicitacoes desc, o.orgao, a.assunto limit ?""",
        [orgao, orgao, limite],
    )


@router.get("/por-bairro", response_model=list[PorBairro])
def por_bairro(
    warehouse: WarehouseDep, regional: str | None = None, limite: Limite = 200
) -> list[dict]:
    """Totais por bairro, somando as regionais em que o bairro aparece."""
    return warehouse.query(
        f"""select l.bairro, count(*) as solicitacoes,
                   count(*) filter (where not f.respondida) as pendentes
            {SOLICITACOES_FROM}
            where ? is null or l.regional = ?
            group by 1 order by solicitacoes desc, l.bairro limit ?""",
        [regional, regional, limite],
    )


@router.get("/tempo-resposta", response_model=list[TempoResposta])
def tempo_resposta(warehouse: WarehouseDep, minimo_solicitacoes: int = 1) -> list[dict]:
    """Por órgão. A mediana só vê as respondidas; compare com os pendentes (viés de censura)."""
    return warehouse.query(
        """select orgao, solicitacoes, respondidas, pendentes, taxa_resposta,
                  mediana_dias_resposta, p90_dias_resposta, mediana_dias_em_aberto
           from marts.agg_tempo_resposta
           where solicitacoes >= ?
           order by solicitacoes desc""",
        [minimo_solicitacoes],
    )


@router.get("/historico-situacao", response_model=list[SituacaoNoSnapshot])
def historico_situacao(warehouse: WarehouseDep, data_inicio: date | None = None) -> list[dict]:
    """Quantidade por situação em cada snapshot (histórico agregado, ADR 0001)."""
    return warehouse.query(
        """select snapshot_data, situacao, sum(quantidade)::bigint as quantidade
           from marts.fct_snapshot_agregado
           where ? is null or snapshot_data >= ?
           group by 1, 2 order by 1, 2""",
        [data_inicio, data_inicio],
    )


@router.get("/dia-semana-mes", response_model=list[DiaSemanaMes])
def dia_semana_mes(warehouse: WarehouseDep) -> list[dict]:
    """Mapa de calor: criadas por mês e dia da semana (a fonte não tem hora)."""
    return warehouse.query(
        """select d.mes, d.nome_mes, d.dia_semana, d.nome_dia_semana,
                  count(*) as solicitacoes
           from marts.fct_solicitacoes as f
           join marts.dim_data as d on f.data_criacao = d.data
           group by all order by d.mes, d.dia_semana"""
    )
