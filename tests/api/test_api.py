import subprocess
import sys

import duckdb
import pytest
from fastapi.testclient import TestClient

from cwbdatasiac.api.main import create_app

pytestmark = pytest.mark.slow


def _get(client, url, **params):
    response = client.get(url, params=params)
    assert response.status_code == 200, response.text
    return response.json()


def test_openapi_lists_every_endpoint(client):
    paths = set(_get(client, "/openapi.json")["paths"])

    assert paths == {
        "/health",
        "/ingestoes",
        "/qualidade",
        "/solicitacoes",
        "/indicadores/resumo",
        "/indicadores/serie-temporal",
        "/indicadores/por-orgao",
        "/indicadores/por-assunto",
        "/indicadores/por-bairro",
        "/indicadores/tempo-resposta",
        "/indicadores/historico-situacao",
        "/indicadores/dia-semana-mes",
    }
    assert client.get("/docs").status_code == 200


def test_health(client):
    assert _get(client, "/health") == {"status": "ok", "ultimo_snapshot": "2026-10-21"}


def test_ingestoes_newest_first_with_filters(client):
    assert [i["run_id"] for i in _get(client, "/ingestoes")] == ["r3", "r2", "r1"]
    assert [i["run_id"] for i in _get(client, "/ingestoes", status="sucesso", limite=1)] == ["r2"]


def test_qualidade_reports_last_load_violations(client):
    body = _get(client, "/qualidade")

    assert body["ultima_ingestao"]["status"] == "falha"
    assert body["ultima_carga"]["run_id"] == "r2"
    assert body["violacoes"] == [
        {
            "regra": "dominio_conhecido",
            "coluna": "Origem",
            "severidade": "alerta",
            "linhas": 1,
            "exemplos": ["WhatsApp"],
        }
    ]


def test_solicitacoes_page_and_order(client):
    body = _get(client, "/solicitacoes", tamanho=2)

    assert body["snapshot_data"] == "2026-10-21"
    assert body["total"] == 5
    assert [i["data_criacao"] for i in body["itens"]] == ["2026-10-02", "2026-10-01"]
    first = body["itens"][0]
    assert first["orgao"] == "Secretaria Municipal da Saúde"
    assert (first["bairro"], first["regional"]) == ("CENTRO", "Matriz")
    assert "logradouro" not in first


def test_solicitacoes_pagination_covers_all_rows(client):
    pages = [_get(client, "/solicitacoes", tamanho=2, pagina=p)["itens"] for p in (1, 2, 3, 4)]

    assert [len(p) for p in pages] == [2, 2, 1, 0]
    assert len({i["solicitacao_sk"] for p in pages for i in p}) == 5


@pytest.mark.parametrize(
    ("params", "total"),
    [
        ({"orgao": "Secretaria Municipal do Meio Ambiente"}, 3),
        ({"bairro": "NÃO INFORMADO"}, 1),
        ({"regional": "Boqueirão"}, 3),
        ({"respondida": False}, 3),
        ({"tipo": "Reclamação", "situacao": "Aberto"}, 1),
        ({"origem": "Telefone"}, 2),
        ({"assunto": "Coleta", "respondida": True}, 1),
        ({"data_inicio": "2026-10-01", "data_fim": "2026-10-01"}, 3),
        ({"orgao": "Inexistente"}, 0),
    ],
)
def test_solicitacoes_filters(client, params, total):
    assert _get(client, "/solicitacoes", **params)["total"] == total


@pytest.mark.parametrize("params", [{"tamanho": 501}, {"pagina": 0}, {"data_inicio": "ontem"}])
def test_solicitacoes_rejects_invalid_params(client, params):
    assert client.get("/solicitacoes", params=params).status_code == 422


def test_resumo(client):
    assert _get(client, "/indicadores/resumo") == {
        "snapshot_data": "2026-10-21",
        "solicitacoes": 5,
        "respondidas": 2,
        "pendentes": 3,
        "taxa_resposta": 0.4,
        "mediana_dias_resposta": 6.0,  # 10 e 2 dias
        "mediana_dias_em_aberto": 20.0,  # 20, 20 e 36 dias
    }


def test_serie_temporal_by_month_and_day(client):
    assert _get(client, "/indicadores/serie-temporal", granularidade="mes") == [
        {"periodo": "2026-09-01", "criadas": 1, "respondidas": 0},
        {"periodo": "2026-10-01", "criadas": 4, "respondidas": 2},
    ]
    daily = _get(client, "/indicadores/serie-temporal", data_inicio="2026-10-01")
    assert daily[0] == {"periodo": "2026-10-01", "criadas": 3, "respondidas": 0}
    assert len(daily) == 21  # dias sem registro aparecem com zero
    assert client.get("/indicadores/serie-temporal?granularidade=ano").status_code == 422


def test_por_orgao_assunto_bairro(client):
    assert _get(client, "/indicadores/por-orgao") == [
        {"orgao": "Secretaria Municipal do Meio Ambiente", "solicitacoes": 3, "pendentes": 2},
        {"orgao": "Secretaria Municipal da Saúde", "solicitacoes": 2, "pendentes": 1},
    ]
    assert _get(client, "/indicadores/por-assunto", orgao="Secretaria Municipal da Saúde") == [
        {"orgao": "Secretaria Municipal da Saúde", "assunto": "Unidade de Saúde", "solicitacoes": 2}
    ]
    assert _get(client, "/indicadores/por-bairro", limite=2) == [
        {"bairro": "XAXIM", "solicitacoes": 3, "pendentes": 2},
        {"bairro": "CENTRO", "solicitacoes": 1, "pendentes": 0},
    ]
    assert _get(client, "/indicadores/por-bairro", regional="Matriz") == [
        {"bairro": "CENTRO", "solicitacoes": 1, "pendentes": 0}
    ]


def test_tempo_resposta(client):
    rows = _get(client, "/indicadores/tempo-resposta")

    assert [r["orgao"] for r in rows] == [
        "Secretaria Municipal do Meio Ambiente",
        "Secretaria Municipal da Saúde",
    ]
    assert rows[1]["mediana_dias_resposta"] == 2.0
    assert rows[1]["mediana_dias_em_aberto"] == 36.0
    assert len(_get(client, "/indicadores/tempo-resposta", minimo_solicitacoes=3)) == 1


def test_historico_situacao(client):
    assert _get(client, "/indicadores/historico-situacao") == [
        {"snapshot_data": "2026-10-20", "situacao": "Aberto", "quantidade": 2},
        {"snapshot_data": "2026-10-20", "situacao": "Concluído", "quantidade": 1},
        {"snapshot_data": "2026-10-21", "situacao": "Aberto", "quantidade": 3},
        {"snapshot_data": "2026-10-21", "situacao": "Concluído", "quantidade": 2},
    ]
    assert len(_get(client, "/indicadores/historico-situacao", data_inicio="2026-10-21")) == 2


def test_dia_semana_mes(client):
    rows = _get(client, "/indicadores/dia-semana-mes")

    assert sum(r["solicitacoes"] for r in rows) == 5
    assert {"mes": 9, "nome_mes": "Setembro", "dia_semana": 2, "nome_dia_semana": "Terça",
            "solicitacoes": 1} in rows  # fmt: skip


def test_missing_warehouse_returns_503(tmp_path):
    client = TestClient(create_app(tmp_path))

    response = client.get("/indicadores/resumo")
    assert response.status_code == 503
    assert response.headers["Retry-After"] == "10"
    assert _get(client, "/health") == {"status": "indisponivel", "ultimo_snapshot": None}


def test_locked_warehouse_returns_503(tmp_path):
    path = tmp_path / "warehouse.duckdb"
    duckdb.connect(str(path)).close()
    holder = subprocess.Popen(
        [
            sys.executable,
            "-c",
            "import duckdb, sys, time; c = duckdb.connect(sys.argv[1]); print('ok', flush=True); "
            "time.sleep(30)",
            str(path),
        ],
        stdout=subprocess.PIPE,
    )
    try:
        holder.stdout.readline()  # o subprocesso já detém o lock de escrita
        assert TestClient(create_app(tmp_path)).get("/ingestoes").status_code == 503
    finally:
        holder.kill()
        holder.wait()
