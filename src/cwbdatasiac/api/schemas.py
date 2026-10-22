"""Modelos de resposta da API (Pydantic v2)."""

from datetime import date, datetime
from enum import StrEnum

from pydantic import BaseModel, Field


class Granularidade(StrEnum):
    dia = "dia"
    semana = "semana"
    mes = "mes"


class Health(BaseModel):
    status: str = Field(description="`ok` ou `indisponivel` (warehouse travado ou ausente)")
    ultimo_snapshot: date | None = None


class Ingestao(BaseModel):
    run_id: str
    snapshot_data: date | None
    arquivo: str | None
    fonte_descoberta: str | None
    inicio: datetime
    fim: datetime | None
    status: str
    etapa_falha: str | None
    mensagem: str | None
    bytes: int | None
    linhas: int | None


class Solicitacao(BaseModel):
    solicitacao_sk: str
    data_criacao: date | None
    data_resposta: date | None
    tipo: str
    situacao: str
    orgao: str
    assunto: str
    subdivisao: str
    bairro: str
    regional: str
    origem: str
    respondida: bool
    dias_ate_resposta: int | None
    dias_em_aberto: int | None


class PaginaSolicitacoes(BaseModel):
    snapshot_data: date | None = Field(description="Snapshot que as linhas retratam")
    total: int
    pagina: int
    tamanho: int
    itens: list[Solicitacao]


class Resumo(BaseModel):
    snapshot_data: date | None
    solicitacoes: int
    respondidas: int
    pendentes: int
    taxa_resposta: float | None
    mediana_dias_resposta: float | None = Field(description="Só entre as respondidas")
    mediana_dias_em_aberto: float | None = Field(description="Só entre as pendentes")


class PontoSerie(BaseModel):
    periodo: date
    criadas: int
    respondidas: int


class PorOrgao(BaseModel):
    orgao: str
    solicitacoes: int
    pendentes: int


class PorAssunto(BaseModel):
    orgao: str
    assunto: str
    solicitacoes: int


class PorBairro(BaseModel):
    bairro: str
    solicitacoes: int
    pendentes: int


class TempoResposta(BaseModel):
    orgao: str
    solicitacoes: int
    respondidas: int
    pendentes: int
    taxa_resposta: float
    mediana_dias_resposta: float | None
    p90_dias_resposta: float | None
    mediana_dias_em_aberto: float | None


class SituacaoNoSnapshot(BaseModel):
    snapshot_data: date
    situacao: str
    quantidade: int


class DiaSemanaMes(BaseModel):
    mes: int
    nome_mes: str
    dia_semana: int = Field(description="1 = segunda … 7 = domingo")
    nome_dia_semana: str
    solicitacoes: int


class Violacao(BaseModel):
    regra: str
    coluna: str | None
    severidade: str
    linhas: int
    exemplos: list[str]


class Qualidade(BaseModel):
    ultima_ingestao: Ingestao | None
    ultima_carga: Ingestao | None = Field(description="Última ingestão com status `sucesso`")
    violacoes: list[Violacao] = Field(description="Violações do contrato na última carga")
