# CwbDataSIAC

[![CI](https://github.com/MelsarDalRiFilho/CwbDataSIAC/actions/workflows/ci.yml/badge.svg)](https://github.com/MelsarDalRiFilho/CwbDataSIAC/actions/workflows/ci.yml)

Pipeline de engenharia de dados sobre os dados abertos da Prefeitura de Curitiba, começando pelo
**SIAC 156**, o Sistema Integrado de Atendimento ao Cidadão. O projeto cobre o caminho completo:
captura da fonte, validação, armazenamento, modelagem com dbt, API em FastAPI e dashboard em
Apache ECharts.

**[Painel ao vivo](https://melsardalrifilho.github.io/CwbDataSIAC/)** ·
[Relatório](https://melsardalrifilho.github.io/CwbDataSIAC/relatorio/) ·
[Linhagem dos dados (dbt)](https://melsardalrifilho.github.io/CwbDataSIAC/dbt/)

> 🚧 Em construção. Veja o [plano por fases](docs/data_siac_plano.md) e o andamento abaixo.

## A fonte

- [Conjunto SIAC 156](https://dadosabertos.curitiba.pr.gov.br/conjuntodado/detalhe/?chave=0d5a7b06-3940-4be9-876e-bc8f23e96530)
  no portal de dados abertos (licença CC BY 4.0), espelhado pela UFPR/C3SL.
- Um CSV por dia, com o **acumulado do ano corrente**: cerca de 626 mil linhas e 123 MB em outubro de 2026.
- Não há número de protocolo e as datas vêm sem hora. Por isso o projeto **não deduplica** e guarda o
  histórico de forma agregada. Detalhes em [ADR 0001](docs/adr/0001-chave-e-historico-das-solicitacoes.md)
  e no [notebook de exploração](notebooks/00_exploracao.ipynb).

## Arquitetura prevista

```mermaid
flowchart LR
    A[Espelho C3SL<br/>156.xml + CSV] --> B[Captura + validação<br/>da execução]
    B --> D[Contrato<br/>Pandera]
    D --> C[Bronze<br/>Parquet]
    C --> E[DuckDB + dbt]
    E --> F[FastAPI]
    F --> G[Dashboard ECharts]
    E --> H[Relatório]
```

## Como rodar

Requisitos: [uv](https://docs.astral.sh/uv/) (instala o Python 3.12 automaticamente) e `make`.

```bash
make install   # dependências + hooks de pre-commit
make check     # lint (ruff) + testes (pytest, cobertura mínima de 80%)
make ingest    # baixa o snapshot mais recente, valida e grava no Bronze
make transform # dbt build: modelos e testes sobre a Bronze
make docs      # documentação e linhagem do dbt (dbt/siac156/target/static_index.html)
make pipeline  # ingest + transform
make api       # API em http://127.0.0.1:8000 (painel em /painel, documentação em /docs)
make report    # relatório em reports/relatorio.html
make site      # site estático em site/ (o que vai para o GitHub Pages)
uv run cwbdatasiac --help
```

### Ingestão

`cwbdatasiac ingest` executa estas etapas, todas registradas em log JSON (`logs/cwbdatasiac.log`) com
o mesmo `run_id` e numa linha da tabela `controle.ingestao_execucoes` (`data/warehouse.duckdb`):

1. **Descoberta** do arquivo do dia: manifesto `156.xml` do espelho C3SL → endpoint JSON do portal
   oficial → navegador headless (Playwright, opcional: `make install-browser`).
2. **Download** com retry e backoff em erros 5xx e de rede, sha256 e escrita atômica.
3. **Checagens:** tipo e tamanho do conteúdo, BOM UTF-8, colunas do cabeçalho, conteúdo idêntico ao
   snapshot anterior e volume (o arquivo acumula o ano, então não pode encolher).
4. **Contrato de entrada (Pandera):** obrigatórios, datas válidas e dentro do ano do snapshot,
   resposta ≥ criação (bloqueantes, com tolerância de 0,1% de linhas) e domínios conhecidos de Tipo,
   Situação, Origem e Regional (só alerta). As violações vão para o log, para
   `controle.contrato_violacoes` e para um relatório JSON em `data/qualidade/`.
5. **Bronze:** Parquet em `data/bronze/siac156/snapshot_data=AAAA-MM-DD/`. O CSV bruto é mantido
   só para as 3 datas mais recentes.

Rodar de novo não duplica nada (status `sem_novidade`). Em caso de falha, o arquivo vai para
`data/quarentena/`, o log registra a etapa e o motivo, e o comando termina com exit code 1.

### Modelagem (dbt)

`cwbdatasiac transform` roda o projeto `dbt/siac156` (dbt-duckdb) e grava em `data/warehouse.duckdb`:

- `staging.stg_siac156__solicitacoes`: tipagem, padronização de nomes por seed e nenhuma deduplicação.
- `marts.fct_solicitacoes`: retrato do último snapshot, uma linha por solicitação, sem endereço.
- `marts.fct_snapshot_agregado`: histórico incremental com contagens por snapshot e dimensões.
- Dimensões `dim_orgao`, `dim_assunto`, `dim_localidade` (bairro × regional), `dim_origem` e `dim_data`.
- Agregados `agg_diario` e `agg_tempo_resposta`. Este último mostra os pendentes ao lado da mediana,
  porque a mediana só enxerga quem já foi respondido.

Os testes de integridade (chaves, relacionamentos, fato e agregado reproduzindo a Bronze) falham o
build; os de qualidade que o contrato de entrada já tolera só avisam.

### API

`cwbdatasiac api` sobe uma FastAPI somente leitura sobre a camada Gold:

| Rota | Conteúdo |
| --- | --- |
| `/health`, `/ingestoes`, `/qualidade` | operação: snapshot servido, execuções e violações do contrato |
| `/solicitacoes` | solicitações do último snapshot, com filtros e paginação (sem endereço) |
| `/indicadores/resumo` | KPIs: total, taxa de resposta, mediana de dias até a resposta e de pendência |
| `/indicadores/serie-temporal` | criadas e respondidas por dia, semana ou mês |
| `/indicadores/por-orgao`, `/por-assunto`, `/por-bairro` | rankings |
| `/indicadores/tempo-resposta` | mediana, p90 e pendentes por órgão |
| `/indicadores/historico-situacao` | situação das solicitações em cada snapshot |
| `/indicadores/dia-semana-mes` | mapa de calor de mês × dia da semana |

A API abre o DuckDB só para leitura e por poucos milissegundos a cada requisição. Enquanto o
pipeline grava, ela responde `503` com `Retry-After`; do outro lado, a ingestão e o dbt esperam o
lock em vez de falhar.

### Painel e relatório

- **Painel (`dashboard/`):** HTML e JavaScript estáticos com Apache ECharts. Mostra KPIs, a série de
  criadas e respondidas, o mapa por bairro, os assuntos mais frequentes, o treemap órgão → assunto,
  o tempo de resposta por órgão, o mapa de calor de mês × dia da semana e a situação em cada
  snapshot. Funciona servido pela API (`/painel`) ou como site estático (lê `data/*.json`).
  - A paleta foi validada para daltonismo nos modos claro e escuro.
  - Todo gráfico tem uma visão em tabela.
- **Relatório:** `cwbdatasiac report` gera um HTML com 7 achados cujos números são recalculados a
  cada execução (canais, concentração da demanda, tempo de resposta e viés de censura, gargalos,
  bairros, sazonalidade e limitações dos dados).
- **Publicação:** o workflow **Pages** (acionado manualmente em *Actions*) roda o pipeline completo
  e publica painel, relatório e linhagem do dbt. Vão para a web só dados agregados.

Divisa de bairros: [IPPUC](https://ippuc.org.br/geodownloads/geo.htm), convertida para GeoJSON por
`scripts/build_bairros_geojson.py`.

Para reexecutar a exploração, baixe os arquivos para `data/raw/` (instruções no início do notebook) e rode `make explore`.

## Andamento

| Fase | Status |
| --- | --- |
| 1. Exploração e decisões | ✅ |
| 2. Esqueleto e CI | ✅ |
| 3. Ingestão, validação da execução e Bronze | ✅ |
| 4. Contrato e validação de entrada | ✅ |
| 5. dbt | ✅ |
| 6. FastAPI | ✅ |
| 7. Dashboard ECharts e relatório | ✅ |
| 8. Automação e vitrine | ⏳ |

## Estrutura

```
src/cwbdatasiac/      código do pipeline (CLI, ingestão, contrato, dbt runner, API, logging)
dbt/siac156/          projeto dbt (staging, marts, seeds, testes)
dashboard/            painel ECharts (estático) e GeoJSON dos bairros
scripts/              conversão da divisa de bairros do IPPUC
tests/                testes pytest (inclui dbt build sobre Bronze sintética)
notebooks/            exploração da fonte
docs/                 demanda, plano e decisões (ADRs)
data/, logs/, site/   gerados localmente, fora do git
```
