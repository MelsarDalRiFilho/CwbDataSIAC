"""Relatório analítico em HTML (Jinja2 + ECharts) com achados calculados dos indicadores.

Recebe o mesmo dicionário que o site exporta (`site.collect`), então números do
relatório e do dashboard sempre coincidem. Os textos são montados a partir dos
dados: quem é o maior órgão, o pior tempo etc. muda conforme o snapshot.
"""

import json
from dataclasses import dataclass, field
from datetime import date
from statistics import mean
from typing import Any

from jinja2 import Environment, PackageLoader, select_autoescape

from cwbdatasiac import __version__

MIN_SOLICITACOES_ORGAO = 1000  # órgãos menores distorcem rankings de taxa e prazo
NAO_INFORMADO = "NÃO INFORMADO"
MESES = [
    "janeiro", "fevereiro", "março", "abril", "maio", "junho",
    "julho", "agosto", "setembro", "outubro", "novembro", "dezembro",
]  # fmt: skip


def orgaos_relevantes(tempo_resposta: list[dict]) -> list[dict]:
    """Órgãos com volume suficiente para rankings; todos, se nenhum atingir o mínimo."""
    grandes = [o for o in tempo_resposta if o["solicitacoes"] >= MIN_SOLICITACOES_ORGAO]
    return grandes or tempo_resposta


@dataclass
class Achado:
    titulo: str
    texto: str
    grafico: str | None = None  # id do gráfico no template
    tabela: list[dict[str, Any]] = field(default_factory=list)

    def colunas_numericas(self) -> list[bool]:
        """Quais colunas da tabela são números (alinhadas à direita no HTML)."""
        return [str(v)[:1].isdigit() for v in self.tabela[0].values()] if self.tabela else []


def inteiro(n: float) -> str:
    return f"{round(n):,}".replace(",", ".")


def pct(x: float, casas: int = 1) -> str:
    return f"{x * 100:.{casas}f}%".replace(".", ",")


def lista_pt(itens: list[str]) -> str:
    """["A", "B", "C"] → "A, B e C"."""
    return " e ".join([", ".join(itens[:-1]), itens[-1]]) if len(itens) > 1 else "".join(itens)


def data_br(iso: str) -> str:
    d = date.fromisoformat(iso)
    return f"{d.day:02d}/{d.month:02d}/{d.year}"


def _volume(d: dict) -> Achado:
    resumo, origens = d["resumo"], d["por_origem"]
    total = resumo["solicitacoes"]
    snapshot = date.fromisoformat(resumo["snapshot_data"])
    dias = (snapshot - date(snapshot.year, 1, 1)).days + 1
    telefone = next((o["solicitacoes"] for o in origens if o["origem"] == "Telefone"), 0)
    return Achado(
        "Volume e canais de entrada",
        f"Até {data_br(resumo['snapshot_data'])}, a Central 156 registrou {inteiro(total)} "
        f"solicitações em {snapshot.year}, cerca de {inteiro(total / dias)} por dia. O telefone "
        f"ainda é o principal canal ({pct(telefone / total)}); os canais digitais somam "
        f"{pct(1 - telefone / total)}.",
        tabela=[
            {
                "Canal": o["origem"],
                "Solicitações": inteiro(o["solicitacoes"]),
                "Participação": pct(o["solicitacoes"] / total),
            }
            for o in origens
        ],
    )


def _concentracao(d: dict) -> Achado:
    total = d["resumo"]["solicitacoes"]
    orgaos, assuntos = d["por_orgao"], d["por_assunto"]
    top3 = sum(o["solicitacoes"] for o in orgaos[:3])
    a = assuntos[0]
    return Achado(
        "Demanda concentrada em poucos órgãos",
        f"{orgaos[0]['orgao']} recebe {pct(orgaos[0]['solicitacoes'] / total)} de todas as "
        f"solicitações, e os três maiores órgãos somam {pct(top3 / total)}. Só o assunto "
        f"“{a['assunto']}” ({a['orgao']}) responde por {pct(a['solicitacoes'] / total)} do total.",
        tabela=[
            {
                "Órgão": o["orgao"],
                "Solicitações": inteiro(o["solicitacoes"]),
                "Participação": pct(o["solicitacoes"] / total),
            }
            for o in orgaos[:10]
        ],
    )


def _tempo(d: dict) -> Achado:
    r = d["resumo"]
    return Achado(
        "Tempo de resposta: o que a mediana não mostra",
        f"{pct(r['taxa_resposta'])} das solicitações já foram respondidas, com mediana de "
        f"{inteiro(r['mediana_dias_resposta'])} dias até a resposta. Mas essa mediana só enxerga "
        f"quem já foi atendido: os {inteiro(r['pendentes'])} pedidos pendentes estão abertos há "
        f"{inteiro(r['mediana_dias_em_aberto'])} dias (mediana). Ignorar os pendentes faz o "
        "atendimento parecer mais rápido do que é, sobretudo nos meses recentes.",
        grafico="tempo_resposta",
    )


def _gargalo(d: dict) -> Achado:
    grandes = orgaos_relevantes(d["tempo_resposta"])
    pior = min(grandes, key=lambda o: o["taxa_resposta"])
    lento = max(grandes, key=lambda o: o["p90_dias_resposta"] or 0)
    recorte = (
        f"Entre os órgãos com ao menos {inteiro(MIN_SOLICITACOES_ORGAO)} solicitações"
        if grandes[0]["solicitacoes"] >= MIN_SOLICITACOES_ORGAO  # houve recorte por volume
        else "Entre todos os órgãos"
    )
    texto = (
        f"{recorte}, "
        f"{pior['orgao']} tem a menor taxa de resposta ({pct(pior['taxa_resposta'])}): "
        f"{inteiro(pior['pendentes'])} pedidos pendentes, abertos há "
        f"{inteiro(pior['mediana_dias_em_aberto'] or 0)} dias (mediana)."
    )
    if lento["orgao"] != pior["orgao"]:
        texto += (
            f" Já o prazo mais longo entre os respondidos é de {lento['orgao']}: 10% das "
            f"respostas levaram mais de {inteiro(lento['p90_dias_resposta'])} dias."
        )
    return Achado(
        "Onde está o gargalo",
        texto,
        tabela=[
            {
                "Órgão": o["orgao"],
                "Taxa de resposta": pct(o["taxa_resposta"]),
                "Pendentes": inteiro(o["pendentes"]),
                "Mediana em aberto (dias)": inteiro(o["mediana_dias_em_aberto"] or 0),
            }
            for o in sorted(grandes, key=lambda o: o["taxa_resposta"])[:8]
        ],
    )


def _bairros(d: dict) -> Achado:
    total = d["resumo"]["solicitacoes"]
    bairros = [b for b in d["por_bairro"] if b["bairro"] != NAO_INFORMADO]
    top3 = bairros[:3]
    nomes = lista_pt([b["bairro"].title() for b in top3])
    verbo = "concentram" if len(top3) > 1 else "concentra"
    parcela = sum(b["solicitacoes"] for b in top3) / total
    return Achado(
        "Bairros com mais demandas",
        f"{nomes} {verbo} {pct(parcela)} das "
        "solicitações. Volume alto acompanha população e atividade comercial, então o ranking "
        "não deve ser lido como qualidade de vida; o mapa no dashboard mostra a cidade inteira.",
        grafico="bairros",
    )


def _sazonalidade(d: dict) -> Achado:
    snapshot = date.fromisoformat(d["resumo"]["snapshot_data"])
    # O mês do snapshot está incompleto: fica fora da comparação.
    completos = [
        m for m in d["serie_mes"] if date.fromisoformat(m["periodo"]).month != snapshot.month
    ]
    pico = max(completos or d["serie_mes"], key=lambda m: m["criadas"])
    dias = [(date.fromisoformat(p["periodo"]), p["criadas"]) for p in d["serie_dia"]]
    uteis = mean([c for dia, c in dias if dia.isoweekday() <= 5] or [0])
    fds = mean([c for dia, c in dias if dia.isoweekday() >= 6] or [0])
    return Achado(
        "Sazonalidade",
        f"{MESES[date.fromisoformat(pico['periodo']).month - 1].capitalize()} foi o mês com mais "
        f"solicitações ({inteiro(pico['criadas'])}). Em dias úteis entram, em média, "
        f"{inteiro(uteis)} pedidos por dia, contra {inteiro(fds)} nos fins de semana"
        + (f" ({pct(fds / uteis, 0)} do volume de um dia útil)." if uteis else "."),
        grafico="serie_mes",
    )


def _dados(d: dict) -> Achado:
    violacoes = d["qualidade"]["violacoes"]
    contrato = (
        "A última carga passou pelo contrato de entrada sem violações."
        if not violacoes
        else f"A última carga registrou {len(violacoes)} violação(ões) de contrato, "
        "detalhadas em /qualidade."
    )
    return Achado(
        "Sobre os dados",
        "A base não tem número de protocolo e as datas não têm hora; linhas idênticas são "
        "solicitações distintas e não foram deduplicadas. Cada arquivo diário traz o ano "
        "corrente acumulado, por isso este relatório retrata o último snapshot. Endereços não "
        f"são publicados: o menor recorte geográfico é o bairro. {contrato}",
    )


def achados(data: dict[str, Any]) -> list[Achado]:
    return [
        builder(data)
        for builder in (_volume, _concentracao, _tempo, _gargalo, _bairros, _sazonalidade, _dados)
    ]


def render_report(data: dict[str, Any]) -> str:
    env = Environment(loader=PackageLoader("cwbdatasiac.report"), autoescape=select_autoescape())
    grandes = orgaos_relevantes(data["tempo_resposta"])
    charts = {
        "serie_mes": data["serie_mes"],
        "tempo_resposta": sorted(grandes, key=lambda o: o["solicitacoes"], reverse=True)[:10],
        "bairros": [b for b in data["por_bairro"] if b["bairro"] != NAO_INFORMADO][:10],
    }
    return env.get_template("relatorio.html.j2").render(
        achados=achados(data),
        snapshot=data_br(data["resumo"]["snapshot_data"]),
        versao=__version__,
        # "</" escapado: o JSON vai dentro de um <script> e não pode fechá-lo.
        charts_json=json.dumps(charts, ensure_ascii=False).replace("</", "<\\/"),
    )
