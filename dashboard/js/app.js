// Painel do SIAC 156. Dois modos de dados, mesmo formato:
// - API (servido por `cwbdatasiac api` em /painel): chama as rotas de SOURCES;
// - estático (GitHub Pages): lê data/<chave>.json, gerado por `cwbdatasiac site`.
// As chaves e rotas abaixo espelham cwbdatasiac.site.SOURCES (um teste garante a paridade).
const SOURCES = {
  health: "/health",
  qualidade: "/qualidade",
  resumo: "/indicadores/resumo",
  serie_dia: "/indicadores/serie-temporal?granularidade=dia",
  serie_semana: "/indicadores/serie-temporal?granularidade=semana",
  serie_mes: "/indicadores/serie-temporal?granularidade=mes",
  por_orgao: "/indicadores/por-orgao?limite=200",
  por_origem: "/indicadores/por-origem",
  por_assunto: "/indicadores/por-assunto?limite=200",
  por_bairro: "/indicadores/por-bairro?limite=200",
  tempo_resposta: "/indicadores/tempo-resposta",
  historico: "/indicadores/historico-situacao",
  calor: "/indicadores/dia-semana-mes",
};

// Cor por entidade, em ordem fixa (nunca pela posição no ranking).
const SITUACOES = ["Concluído", "Respondido", "Em andamento", "Em avaliação", "Aberto", "Falta de dados"];
const DIAS = ["Seg", "Ter", "Qua", "Qui", "Sex", "Sáb", "Dom"];
const TOP_ORGAOS_TREEMAP = 8;
const MIN_SOLICITACOES_TEMPO = 1000;
const RETRY_MS = 10_000;

const fmt = new Intl.NumberFormat("pt-BR");
const pct = new Intl.NumberFormat("pt-BR", { style: "percent", maximumFractionDigits: 1 });
const dataBR = (iso) => iso.split("-").reverse().join("/");
const root = document.querySelector(".viz-root");
const css = (name) => getComputedStyle(root).getPropertyValue(name).trim();

// ---------- dados ----------

async function detectMode() {
  try {
    const r = await fetch("data/manifest.json", { cache: "no-store" });
    return r.ok ? "estatico" : "api";
  } catch {
    return "api";
  }
}

async function fetchJSON(url) {
  for (;;) {
    const r = await fetch(url);
    if (r.status !== 503) {
      if (!r.ok) throw new Error(`${url}: HTTP ${r.status}`);
      aviso(null);
      return r.json();
    }
    aviso("Os dados estão sendo atualizados. Nova tentativa em alguns segundos…");
    await new Promise((ok) => setTimeout(ok, RETRY_MS));
  }
}

async function loadAll(mode) {
  const entries = await Promise.all(
    Object.entries(SOURCES).map(async ([key, route]) => [
      key,
      await fetchJSON(mode === "estatico" ? `data/${key}.json` : route),
    ]),
  );
  const data = Object.fromEntries(entries);
  data.geo = await fetchJSON("geo/bairros.geojson");
  return data;
}

function aviso(texto) {
  const el = document.getElementById("aviso");
  el.hidden = !texto;
  el.textContent = texto ?? "";
}

// ---------- tema e peças comuns ----------

function theme() {
  return {
    surface: css("--surface-1"),
    primary: css("--text-primary"),
    secondary: css("--text-secondary"),
    muted: css("--text-muted"),
    grid: css("--grid"),
    axis: css("--axis"),
    series: [1, 2, 3, 4, 5, 6].map((i) => css(`--series-${i}`)),
    seriesStrong: css("--series-1-strong"),
    seq: [css("--seq-min"), css("--seq-max")],
  };
}

function base(t) {
  return {
    textStyle: { fontFamily: "system-ui, -apple-system, 'Segoe UI', sans-serif", color: t.secondary },
    grid: { left: 8, right: 24, top: 36, bottom: 8, containLabel: true },
    // Legenda só nos painéis com 2+ séries (cada painel liga com `legenda(t)`).
    legend: { show: false },
    tooltip: {
      backgroundColor: t.surface,
      borderColor: t.grid,
      textStyle: { color: t.primary },
      valueFormatter: (v) => (v == null ? "—" : fmt.format(v)),
    },
  };
}

const MES_CURTO = new Intl.DateTimeFormat("pt-BR", { month: "short", timeZone: "UTC" });
const tickData = (v) => {
  const d = new Date(v);
  const mes = MES_CURTO.format(d).replace(".", "");
  return d.getUTCDate() === 1 ? mes : `${d.getUTCDate()} ${mes}`;
};

const legenda = (t) => ({
  show: true, top: 0, left: 0, icon: "roundRect", textStyle: { color: t.secondary },
});

const axis = (t, extra = {}) => {
  const formatter =
    extra.type === "value" ? (v) => fmt.format(v) : extra.type === "time" ? tickData : undefined;
  return {
    axisLine: { lineStyle: { color: t.axis } },
    axisTick: { show: false },
    splitLine: { lineStyle: { color: t.grid } },
    ...extra,
    axisLabel: { color: t.muted, ...(formatter && { formatter }), ...extra.axisLabel },
  };
};

// ---------- painéis: cada um devolve { option, table: { columns, rows } } ----------

const PAINEIS = {
  serie(d, t, estado) {
    const pontos = d[`serie_${estado.granularidade}`];
    const serie = (name, key, color) => ({
      name, type: "line", color, showSymbol: pontos.length < 60, symbolSize: 8,
      data: pontos.map((p) => [p.periodo, p[key]]), lineStyle: { width: 2 },
      endLabel: { show: true, formatter: name, color: t.secondary },
      labelLayout: { moveOverlap: "shiftY" },
    });
    return {
      option: {
        ...base(t),
        legend: legenda(t),
        tooltip: { ...base(t).tooltip, trigger: "axis" },
        grid: { ...base(t).grid, right: 100 },
        xAxis: axis(t, { type: "time", splitLine: { show: false } }),
        yAxis: axis(t, { type: "value" }),
        series: [serie("Criadas", "criadas", t.series[0]), serie("Respondidas", "respondidas", t.series[1])],
      },
      table: {
        columns: [["Período", "periodo"], ["Criadas", "criadas", true], ["Respondidas", "respondidas", true]],
        rows: pontos,
      },
    };
  },

  mapa(d, t) {
    const nomes = Object.fromEntries(d.geo.features.map((f) => [f.properties.chave, f.properties.nome]));
    const valores = d.por_bairro.filter((b) => b.bairro in nomes);
    return {
      option: {
        ...base(t),
        tooltip: {
          ...base(t).tooltip, trigger: "item",
          formatter: (p) => `${nomes[p.name] ?? p.name}<br>${fmt.format(p.value || 0)} solicitações`,
        },
        visualMap: {
          type: "continuous", min: 0, max: Math.max(...valores.map((b) => b.solicitacoes)),
          inRange: { color: t.seq }, left: 0, bottom: 0, calculable: false,
          text: ["mais", "menos"], textStyle: { color: t.muted }, formatter: (v) => fmt.format(v),
        },
        series: [{
          type: "map", map: "curitiba", roam: true, name: "Solicitações", showLegendSymbol: false,
          layoutCenter: ["55%", "50%"], layoutSize: "95%",
          itemStyle: { borderColor: t.surface, borderWidth: 1 },
          emphasis: { label: { show: false }, itemStyle: { borderColor: t.primary, borderWidth: 1.5 } },
          select: { disabled: true },
          data: valores.map((b) => ({ name: b.bairro, value: b.solicitacoes })),
        }],
      },
      table: {
        columns: [["Bairro", "bairro"], ["Solicitações", "solicitacoes", true], ["Pendentes", "pendentes", true]],
        rows: d.por_bairro,
      },
    };
  },

  assuntos(d, t) {
    const top = d.por_assunto.slice(0, 15).reverse();
    return {
      option: {
        ...base(t),
        tooltip: {
          ...base(t).tooltip, trigger: "item",
          formatter: (p) => `${top[p.dataIndex].assunto}<br>${top[p.dataIndex].orgao}<br>${fmt.format(p.value)}`,
        },
        grid: { ...base(t).grid, top: 8, right: 64 },
        xAxis: axis(t, { type: "value" }),
        yAxis: axis(t, {
          type: "category", data: top.map((a) => a.assunto), splitLine: { show: false },
          axisLabel: { color: t.muted, width: 180, overflow: "truncate" },
        }),
        series: [{
          type: "bar", name: "Solicitações", color: t.series[0], barCategoryGap: "30%",
          itemStyle: { borderRadius: [0, 4, 4, 0] }, data: top.map((a) => a.solicitacoes),
          label: { show: true, position: "right", color: t.secondary, formatter: (p) => fmt.format(p.value) },
        }],
      },
      table: {
        columns: [["Assunto", "assunto"], ["Órgão", "orgao"], ["Solicitações", "solicitacoes", true]],
        rows: d.por_assunto.slice(0, 15),
      },
    };
  },

  treemap(d, t) {
    const principais = d.por_orgao.slice(0, TOP_ORGAOS_TREEMAP);
    const nos = principais.map((o) => {
      const filhos = d.por_assunto
        .filter((a) => a.orgao === o.orgao)
        .map((a) => ({ name: a.assunto, value: a.solicitacoes }));
      const resto = o.solicitacoes - filhos.reduce((s, f) => s + f.value, 0);
      if (resto > 0) filhos.push({ name: "Outros assuntos", value: resto });
      return { name: o.orgao, value: o.solicitacoes, children: filhos };
    });
    const outros = d.por_orgao.slice(TOP_ORGAOS_TREEMAP).reduce((s, o) => s + o.solicitacoes, 0);
    if (outros > 0) nos.push({ name: "Outros órgãos", value: outros });
    return {
      option: {
        ...base(t),
        tooltip: { ...base(t).tooltip, formatter: (p) => `${p.treePathInfo.slice(1).map((n) => n.name).join(" › ")}<br>${fmt.format(p.value)}` },
        series: [{
          type: "treemap", name: "Solicitações", data: nos, roam: false, nodeClick: "zoomToNode",
          leafDepth: 2, top: 8, left: 0, right: 0, bottom: 32,
          breadcrumb: { bottom: 0, itemStyle: { color: t.surface, borderColor: t.grid, textStyle: { color: t.secondary } } },
          label: { color: "#fff", overflow: "truncate" },
          levels: [
            // raiz: um único tom; a área codifica o volume e o rótulo, a identidade
            { color: [t.series[0]], itemStyle: { borderWidth: 0, gapWidth: 4, borderColor: t.surface } },
            // órgãos: moldura em tom mais escuro, com o nome no cabeçalho
            {
              itemStyle: { borderColor: t.seriesStrong, borderWidth: 4, gapWidth: 2 },
              upperLabel: { show: true, height: 22, color: "#fff", fontWeight: 600 },
            },
            // assuntos
            { itemStyle: { borderWidth: 0 } },
          ],
        }],
      },
      table: {
        columns: [["Órgão", "orgao"], ["Solicitações", "solicitacoes", true], ["Pendentes", "pendentes", true]],
        rows: d.por_orgao,
      },
    };
  },

  tempo(d, t) {
    const orgaos = d.tempo_resposta
      .filter((o) => o.solicitacoes >= MIN_SOLICITACOES_TEMPO)
      .slice(0, 10)
      .reverse();
    const barra = (name, key, color) => ({
      name, type: "bar", color, data: orgaos.map((o) => o[key]),
      itemStyle: { borderRadius: [0, 4, 4, 0], borderColor: t.surface, borderWidth: 1 },
    });
    return {
      option: {
        ...base(t),
        tooltip: {
          ...base(t).tooltip, trigger: "axis", axisPointer: { type: "shadow" },
          valueFormatter: (v) => (v == null ? "—" : `${fmt.format(v)} dias`),
        },
        legend: legenda(t),
        xAxis: axis(t, { type: "value" }),
        yAxis: axis(t, {
          type: "category", data: orgaos.map((o) => o.orgao), splitLine: { show: false },
          axisLabel: { color: t.muted, width: 190, overflow: "truncate" },
        }),
        series: [barra("Mediana", "mediana_dias_resposta", t.series[0]), barra("p90", "p90_dias_resposta", t.series[1])],
      },
      table: {
        columns: [
          ["Órgão", "orgao"], ["Solicitações", "solicitacoes", true], ["Taxa de resposta", "taxa_resposta", "pct"],
          ["Mediana (dias)", "mediana_dias_resposta", true], ["p90 (dias)", "p90_dias_resposta", true],
          ["Pendentes", "pendentes", true], ["Mediana em aberto (dias)", "mediana_dias_em_aberto", true],
        ],
        rows: d.tempo_resposta,
      },
    };
  },

  calor(d, t) {
    const meses = [...new Map(d.calor.map((c) => [c.mes, c.nome_mes])).values()];
    return {
      option: {
        ...base(t),
        tooltip: {
          ...base(t).tooltip, trigger: "item",
          formatter: (p) => `${meses[p.value[1]]}, ${DIAS[p.value[0]]}<br>${fmt.format(p.value[2])}`,
        },
        grid: { ...base(t).grid, top: 8, bottom: 48 },
        xAxis: axis(t, { type: "category", data: DIAS, splitLine: { show: false } }),
        yAxis: axis(t, { type: "category", data: meses, inverse: true, splitLine: { show: false } }),
        visualMap: {
          min: 0, max: Math.max(...d.calor.map((c) => c.solicitacoes)), inRange: { color: t.seq },
          orient: "horizontal", left: "center", bottom: 0, itemHeight: 160, calculable: false,
          text: ["mais", "menos"],
          textStyle: { color: t.muted }, formatter: (v) => fmt.format(v),
        },
        series: [{
          type: "heatmap", name: "Solicitações",
          itemStyle: { borderColor: t.surface, borderWidth: 2, borderRadius: 4 },
          data: d.calor.map((c) => [c.dia_semana - 1, meses.indexOf(c.nome_mes), c.solicitacoes]),
        }],
      },
      table: {
        columns: [["Mês", "nome_mes"], ["Dia", "nome_dia_semana"], ["Solicitações", "solicitacoes", true]],
        rows: d.calor,
      },
    };
  },

  historico(d, t) {
    const snapshots = [...new Set(d.historico.map((h) => h.snapshot_data))];
    const valor = (s, sit) => d.historico.find((h) => h.snapshot_data === s && h.situacao === sit)?.quantidade ?? 0;
    return {
      option: {
        ...base(t),
        legend: legenda(t),
        tooltip: { ...base(t).tooltip, trigger: "axis", axisPointer: { type: "shadow" } },
        xAxis: axis(t, { type: "category", data: snapshots.map(dataBR), splitLine: { show: false } }),
        yAxis: axis(t, { type: "value" }),
        series: SITUACOES.map((sit, i) => ({
          name: sit, type: "bar", stack: "situacao", color: t.series[i], barMaxWidth: 48,
          itemStyle: { borderColor: t.surface, borderWidth: 1 },
          data: snapshots.map((s) => valor(s, sit)),
        })),
      },
      table: {
        columns: [["Snapshot", "snapshot_data"], ["Situação", "situacao"], ["Quantidade", "quantidade", true]],
        rows: d.historico,
      },
    };
  },
};

// ---------- montagem ----------

function kpis(d) {
  const r = d.resumo;
  const tiles = [
    ["Solicitações no ano", fmt.format(r.solicitacoes), `até ${dataBR(r.snapshot_data)}`],
    ["Taxa de resposta", pct.format(r.taxa_resposta), `${fmt.format(r.respondidas)} respondidas`],
    ["Pendentes", fmt.format(r.pendentes), "ainda sem resposta"],
    ["Mediana até a resposta", `${fmt.format(r.mediana_dias_resposta)} dias`, "entre as respondidas"],
    ["Mediana em aberto", `${fmt.format(r.mediana_dias_em_aberto)} dias`, "entre as pendentes"],
  ];
  document.getElementById("kpis").innerHTML = tiles
    .map(([rotulo, valor, nota]) =>
      `<div class="kpi"><div class="rotulo">${rotulo}</div><div class="valor">${valor}</div><div class="nota">${nota}</div></div>`)
    .join("");
}

function tabelaHTML({ columns, rows }) {
  const cell = (v, kind) => (kind === "pct" ? pct.format(v) : kind ? fmt.format(v ?? 0) : v ?? "—");
  const head = columns.map(([label, , kind]) => `<th${kind ? ' class="num"' : ""}>${label}</th>`).join("");
  const body = rows
    .map((r) => `<tr>${columns.map(([, key, kind]) => `<td${kind ? ' class="num"' : ""}>${cell(r[key], kind)}</td>`).join("")}</tr>`)
    .join("");
  return `<table><thead><tr>${head}</tr></thead><tbody>${body}</tbody></table>`;
}

function montarCartao(card) {
  const botao = document.createElement("button");
  botao.type = "button";
  botao.className = "alternar";
  botao.textContent = "Ver tabela";
  botao.setAttribute("aria-expanded", "false");
  const tabela = document.createElement("div");
  tabela.className = "tabela";
  tabela.hidden = true;
  const grafico = card.querySelector(".grafico");
  botao.addEventListener("click", () => {
    const mostrar = tabela.hidden;
    tabela.hidden = !mostrar;
    grafico.hidden = mostrar;
    botao.textContent = mostrar ? "Ver gráfico" : "Ver tabela";
    botao.setAttribute("aria-expanded", String(mostrar));
  });
  card.querySelector("h2").after(botao);
  card.append(tabela);
  return tabela;
}

async function main() {
  const mode = await detectMode();
  if (mode === "api") {
    // Servido pela API: relatório e linhagem só existem no site estático.
    document.getElementById("link-relatorio").remove();
    document.getElementById("link-dbt").remove();
  }
  const d = await loadAll(mode);
  // registerMap usa a propriedade "name"; a nossa chave de junção é "chave".
  echarts.registerMap("curitiba", {
    ...d.geo,
    features: d.geo.features.map((f) => ({ ...f, properties: { ...f.properties, name: f.properties.chave } })),
  });

  document.getElementById("subtitulo").textContent =
    `Dados abertos da Prefeitura · snapshot de ${dataBR(d.resumo.snapshot_data)}` +
    (mode === "api" ? " · servido pela API local" : "");
  const q = d.qualidade;
  document.getElementById("qualidade").textContent = q.ultima_carga
    ? `Última carga: ${dataBR(q.ultima_carga.snapshot_data)}, ${q.violacoes.length} violação(ões) de contrato.`
    : "";
  kpis(d);

  const estado = { granularidade: "semana" };
  const cartoes = [...document.querySelectorAll("[data-painel]")].map((card) => ({
    nome: card.dataset.painel,
    tabela: montarCartao(card),
    chart: echarts.init(card.querySelector(".grafico")),
  }));

  const desenhar = () => {
    const t = theme();
    for (const c of cartoes) {
      const { option, table } = PAINEIS[c.nome](d, t, estado);
      c.chart.setOption(option, true);
      c.tabela.innerHTML = tabelaHTML(table);
    }
  };
  desenhar();

  document.querySelectorAll("[data-granularidade]").forEach((botao) =>
    botao.addEventListener("click", () => {
      estado.granularidade = botao.dataset.granularidade;
      document.querySelectorAll("[data-granularidade]").forEach((b) => b.setAttribute("aria-pressed", String(b === botao)));
      desenhar();
    }),
  );
  window.addEventListener("resize", () => cartoes.forEach((c) => c.chart.resize()));
  matchMedia("(prefers-color-scheme: dark)").addEventListener("change", desenhar);
}

main().catch((erro) => {
  console.error(erro);
  aviso(`Não foi possível carregar os dados (${erro.message}).`);
});
