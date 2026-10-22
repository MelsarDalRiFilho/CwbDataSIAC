from datetime import date

import pyarrow as pa
import pytest

from cwbdatasiac.config import EXPECTED_COLUMNS
from cwbdatasiac.validation.contracts import validate

SNAPSHOT = date(2026, 10, 20)
BASE = {
    "Tipo": "Solicitação",
    "Orgao": "Secretaria Municipal do Meio Ambiente",
    "DataCriacao": "23/07/2026",
    "Assunto": "Coleta",
    "Subdivisao": "Entulhos",
    "Situacao": "Concluído",
    "Logradouro": "Rua Exemplo",
    "Bairro": "XAXIM",
    "Regional": "Unidade Regional Boqueirao",
    "DataResposta": "31/07/2026",
    "Origem": "App 156",
}


def _table(*overrides: dict, valid_rows: int = 0) -> pa.Table:
    rows = [{**BASE, **o} for o in overrides] + [BASE] * valid_rows
    return pa.table({c: pa.array([r[c] for r in rows], pa.string()) for c in EXPECTED_COLUMNS})


def _rules(result):
    return {(v.regra, v.coluna, v.severidade): v for v in result.violacoes}


def test_valid_rows_pass():
    result = validate(_table(valid_rows=3), SNAPSHOT, tolerance=0.0)

    assert result.violacoes == []
    assert result.linhas == 3
    assert not result.bloqueado


def test_known_nullable_columns_accept_nulls():
    overrides = {"Bairro": None, "Regional": None, "Logradouro": None, "DataResposta": None}

    assert validate(_table(overrides), SNAPSHOT, 0.0).violacoes == []


@pytest.mark.parametrize(
    ("override", "rule", "column", "example"),
    [
        ({"Tipo": None}, "not_nullable", "Tipo", "<nulo>"),
        ({"DataCriacao": "31/02/2026"}, "data_valida", "DataCriacao", "31/02/2026"),
        ({"DataCriacao": "2026-07-23"}, "data_valida", "DataCriacao", "2026-07-23"),
        ({"DataCriacao": "15/12/2025"}, "data_no_ano_do_snapshot", "DataCriacao", "15/12/2025"),
        ({"DataResposta": "21/10/2026"}, "data_no_ano_do_snapshot", "DataResposta", "21/10/2026"),
    ],
)
def test_blocking_rules(override, rule, column, example):
    result = validate(_table(override, valid_rows=1), SNAPSHOT, tolerance=0.0)

    violacao = _rules(result)[(rule, column, "bloqueante")]
    assert violacao.linhas == 1
    assert violacao.exemplos == [example]
    assert result.linhas_invalidas == 1
    assert result.bloqueado


def test_answer_before_creation_shows_only_date_columns():
    result = validate(_table({"DataResposta": "01/01/2026"}), SNAPSHOT, 0.0)

    violacao = _rules(result)[("resposta_apos_criacao", None, "bloqueante")]
    assert violacao.exemplos == ["DataCriacao=23/07/2026 DataResposta=01/01/2026"]


def test_invalid_date_is_not_counted_again_by_cross_rule():
    result = validate(_table({"DataCriacao": "99/99/2026"}), SNAPSHOT, 0.0)

    assert [v.regra for v in result.violacoes] == ["data_valida"]


def test_row_violating_several_rules_counts_once():
    result = validate(_table({"Tipo": None, "DataCriacao": "15/12/2025"}), SNAPSHOT, 0.0)

    assert len(result.violacoes) == 2
    assert result.linhas_invalidas == 1


def test_unknown_domain_value_only_alerts():
    result = validate(_table({"Origem": "WhatsApp"}, valid_rows=1), SNAPSHOT, tolerance=0.0)

    violacao = _rules(result)[("dominio_conhecido", "Origem", "alerta")]
    assert violacao.exemplos == ["WhatsApp"]
    assert result.linhas_invalidas == 0
    assert not result.bloqueado


def test_tolerance_decides_blocking():
    table = _table({"Tipo": None}, valid_rows=9)  # 10% inválido

    assert not validate(table, SNAPSHOT, tolerance=0.10).bloqueado
    assert validate(table, SNAPSHOT, tolerance=0.05).bloqueado


def test_wrong_column_type_is_structural_and_always_blocks():
    table = _table(valid_rows=2).set_column(0, "Tipo", pa.array([1, 2], pa.int64()))

    result = validate(table, SNAPSHOT, tolerance=1.0)

    assert result.estrutural
    assert result.bloqueado


def test_sensitive_column_never_appears_in_examples():
    table = _table(
        {"Logradouro": "Rua Secreta", "DataResposta": "01/01/2026", "Origem": "WhatsApp"}
    )

    result = validate(table, SNAPSHOT, 0.0)

    assert "Rua Secreta" not in str(result.to_dict())


def test_summary_and_serialization():
    result = validate(_table({"Tipo": None}, valid_rows=3), SNAPSHOT, tolerance=0.5)

    assert result.resumo().startswith("1 de 4 linhas inválidas (25.0000%")
    assert "not_nullable(Tipo)=1" in result.resumo()
    data = result.to_dict()
    assert data["snapshot_data"] == "2026-10-20"
    assert data["percentual_invalido"] == 0.25
    assert data["bloqueado"] is False


def test_empty_table_has_zero_invalid_fraction():
    result = validate(_table(), SNAPSHOT, tolerance=0.0)

    assert result.percentual_invalido == 0.0
    assert not result.bloqueado
