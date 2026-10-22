"""Contrato de entrada do SIAC 156, validado com Pandera antes de promover o snapshot.

Duas severidades:

- **bloqueante**: regras estruturais (obrigatórios, datas, coerência entre datas).
  Se a fração de linhas que viola alguma delas passar da tolerância, o snapshot é
  rejeitado. Abaixo da tolerância, as linhas são carregadas como vieram (ADR 0001:
  não descartamos linhas) e as violações ficam registradas.
- **alerta**: valores fora dos domínios conhecidos (um canal novo de Origem, por
  exemplo, é legítimo). Só gera aviso e relatório.

Os exemplos do relatório mostram apenas as colunas da regra violada. `Logradouro`
nunca aparece, porque contém endereço (LGPD).
"""

from dataclasses import asdict, dataclass, field
from datetime import date

import pandas as pd
import pandera.pandas as pa
import pyarrow as pa_arrow
from pandera.errors import SchemaErrors

from cwbdatasiac.config import EXPECTED_COLUMNS

DATE_FORMAT = "%d/%m/%Y"
MAX_EXAMPLES = 5
SENSITIVE_COLUMNS = frozenset({"Logradouro"})

# O dicionário marca Bairro e Logradouro como NOT NULL, mas a fonte tem nulos
# legítimos (93 e 1 linhas em 20/10/2026); por isso não entram aqui.
REQUIRED_COLUMNS = ("Tipo", "Orgao", "DataCriacao", "Assunto", "Subdivisao", "Situacao", "Origem")

KNOWN_DOMAINS = {
    "Tipo": [
        "Solicitação",
        "Reclamação",
        "Denúncia",
        "Elogio",
        "Sugestão",
        "Recadastro",
        "Informação",
    ],
    "Situacao": [
        "Concluído",
        "Aberto",
        "Em andamento",
        "Respondido",
        "Em avaliação",
        "Falta de dados",
    ],
    "Origem": ["Telefone", "App 156", "Portal", "Chat", "App Curitiba"],
    "Regional": [
        f"Unidade Regional {nome}"
        for nome in (
            "Matriz",
            "Boa Vista",
            "Portao",
            "Cajuru",
            "Boqueirao",
            "Pinheirinho",
            "Santa Felicidade",
            "CIC",
            "Bairro Novo",
            "Tatuquara",
        )
    ],
}

# Regras de DataFrame (várias colunas): quais colunas mostrar como exemplo.
WIDE_RULE_COLUMNS = {"resposta_apos_criacao": ("DataCriacao", "DataResposta")}


def _parse(series: pd.Series) -> pd.Series:
    return pd.to_datetime(series, format=DATE_FORMAT, errors="coerce")


def _answered_after_created(df: pd.DataFrame) -> pd.Series:
    created, answered = _parse(df["DataCriacao"]), _parse(df["DataResposta"])
    # Datas inválidas já são apontadas por `data_valida`; aqui não contam de novo.
    return created.isna() | answered.isna() | (answered >= created)


def blocking_schema(snapshot_date: date) -> pa.DataFrameSchema:
    year_start, snapshot = pd.Timestamp(snapshot_date.year, 1, 1), pd.Timestamp(snapshot_date)
    date_checks = [
        pa.Check(lambda s: _parse(s).notna(), name="data_valida"),
        # O arquivo acumula o ano corrente: nenhuma data fora de [1º/jan, data do snapshot].
        pa.Check(
            lambda s: _parse(s).isna() | _parse(s).between(year_start, snapshot),
            name="data_no_ano_do_snapshot",
        ),
    ]

    columns = {c: pa.Column(str, nullable=c not in REQUIRED_COLUMNS) for c in EXPECTED_COLUMNS}
    columns["DataCriacao"] = pa.Column(str, nullable=False, checks=date_checks)
    columns["DataResposta"] = pa.Column(str, nullable=True, checks=date_checks)
    return pa.DataFrameSchema(
        columns,
        checks=[pa.Check(_answered_after_created, name="resposta_apos_criacao")],
    )


def alert_schema() -> pa.DataFrameSchema:
    return pa.DataFrameSchema(
        {
            column: pa.Column(str, nullable=True, checks=pa.Check.isin(values))
            for column, values in KNOWN_DOMAINS.items()
        }
    )


@dataclass(frozen=True)
class Violacao:
    regra: str
    coluna: str | None
    severidade: str  # bloqueante | alerta
    linhas: int
    exemplos: list[str]


@dataclass
class ResultadoContrato:
    snapshot_data: date
    linhas: int
    tolerancia: float
    linhas_invalidas: int = 0
    estrutural: bool = False  # tipo de coluna errado ou falha sem linha associada
    violacoes: list[Violacao] = field(default_factory=list)

    @property
    def percentual_invalido(self) -> float:
        return self.linhas_invalidas / self.linhas if self.linhas else 0.0

    @property
    def bloqueado(self) -> bool:
        return self.estrutural or self.percentual_invalido > self.tolerancia

    def resumo(self) -> str:
        bloqueantes = [v for v in self.violacoes if v.severidade == "bloqueante"]
        regras = ", ".join(f"{v.regra}({v.coluna or '*'})={v.linhas}" for v in bloqueantes)
        return (
            f"{self.linhas_invalidas} de {self.linhas} linhas inválidas "
            f"({self.percentual_invalido:.4%}, tolerância {self.tolerancia:.4%}): {regras}"
        )

    def to_dict(self) -> dict:
        return {
            **asdict(self),
            "snapshot_data": self.snapshot_data.isoformat(),
            "percentual_invalido": self.percentual_invalido,
            "bloqueado": self.bloqueado,
        }


def _failure_cases(schema: pa.DataFrameSchema, df: pd.DataFrame) -> pd.DataFrame:
    try:
        schema.validate(df, lazy=True)
    except SchemaErrors as exc:
        return exc.failure_cases
    return pd.DataFrame(columns=["schema_context", "column", "check", "failure_case", "index"])


def _summarize(cases: pd.DataFrame, severidade: str) -> list[Violacao]:
    violacoes = []
    for check, group in cases.groupby("check", sort=True):
        # O Pandera nomeia o isin pela lista de valores; um nome estável é melhor no relatório.
        rule = "dominio_conhecido" if str(check).startswith("isin(") else str(check)
        if group["schema_context"].eq("DataFrameSchema").all():
            # Regra de várias colunas: o Pandera devolve a linha inteira; mostramos só as da regra.
            shown = group[group["column"].isin(WIDE_RULE_COLUMNS.get(rule, ()))]
            examples = [
                " ".join(
                    f"{c}={v}" for c, v in zip(row["column"], row["failure_case"], strict=True)
                )
                for _, row in list(shown.groupby("index", sort=True))[:MAX_EXAMPLES]
            ]
            violacoes.append(
                Violacao(rule, None, severidade, int(group["index"].nunique()), examples)
            )
            continue
        for column, by_column in group.groupby("column", sort=True):
            examples = []
            if column not in SENSITIVE_COLUMNS:
                values = by_column["failure_case"].astype("string").fillna("<nulo>")
                examples = values.drop_duplicates().head(MAX_EXAMPLES).tolist()
            linhas = int(by_column["index"].nunique())
            violacoes.append(Violacao(rule, str(column), severidade, linhas, examples))
    return violacoes


def validate(table: pa_arrow.Table, snapshot_date: date, tolerance: float) -> ResultadoContrato:
    df = table.select(list(EXPECTED_COLUMNS)).to_pandas()
    result = ResultadoContrato(snapshot_date, len(df), tolerance)

    blocking = _failure_cases(blocking_schema(snapshot_date), df)
    # Tipo de coluna errado (o Pandera reporta por linha) ou falha sem linha associada
    # indicam mudança de estrutura: bloqueiam independentemente da tolerância.
    wrong_type = blocking["check"].astype("string").str.startswith("dtype(")
    result.estrutural = bool((blocking["index"].isna() | wrong_type).any())
    result.linhas_invalidas = int(blocking["index"].dropna().nunique())
    result.violacoes = _summarize(blocking, "bloqueante") + _summarize(
        _failure_cases(alert_schema(), df), "alerta"
    )
    return result
