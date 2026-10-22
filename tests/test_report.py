import pytest

from cwbdatasiac.report import (
    MIN_SOLICITACOES_ORGAO,
    Achado,
    data_br,
    inteiro,
    lista_pt,
    orgaos_relevantes,
    pct,
)


def test_number_formats_are_brazilian():
    assert inteiro(1234567.4) == "1.234.567"
    assert pct(0.8866) == "88,7%"
    assert pct(0.456, 0) == "46%"
    assert data_br("2026-10-21") == "21/10/2026"


@pytest.mark.parametrize(
    ("itens", "texto"),
    [(["A"], "A"), (["A", "B"], "A e B"), (["A", "B", "C"], "A, B e C"), ([], "")],
)
def test_lista_pt(itens, texto):
    assert lista_pt(itens) == texto


def test_orgaos_relevantes_falls_back_to_all():
    pequenos = [{"solicitacoes": 10}, {"solicitacoes": 20}]
    grande = {"solicitacoes": MIN_SOLICITACOES_ORGAO}

    assert orgaos_relevantes(pequenos) == pequenos
    assert orgaos_relevantes([*pequenos, grande]) == [grande]


def test_numeric_columns_detected_from_first_row():
    achado = Achado("t", "x", tabela=[{"Órgão": "SMMA", "Total": "1.234", "Taxa": "88,7%"}])

    assert achado.colunas_numericas() == [False, True, True]
    assert Achado("t", "x").colunas_numericas() == []
