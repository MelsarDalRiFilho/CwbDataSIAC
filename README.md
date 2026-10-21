# CwbDataSIAC

[![CI](https://github.com/MelsarDalRiFilho/CwbDataSIAC/actions/workflows/ci.yml/badge.svg)](https://github.com/MelsarDalRiFilho/CwbDataSIAC/actions/workflows/ci.yml)

Pipeline de engenharia de dados sobre os dados abertos da Prefeitura de Curitiba, começando pelo
**SIAC 156**, o Sistema Integrado de Atendimento ao Cidadão. O projeto cobre o caminho completo:
captura da fonte, validação, armazenamento, modelagem com dbt, API em FastAPI e dashboard em
Apache ECharts.

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
    B --> C[Bronze<br/>Parquet]
    C --> D[Contrato<br/>Pandera]
    D --> E[DuckDB + dbt]
    E --> F[FastAPI]
    F --> G[Dashboard ECharts]
    E --> H[Relatório]
```

## Como rodar

Requisitos: [uv](https://docs.astral.sh/uv/) (instala o Python 3.12 automaticamente) e `make`.

```bash
make install   # dependências + hooks de pre-commit
make check     # lint (ruff) + testes (pytest, cobertura mínima de 80%)
uv run cwbdatasiac --help
```

Para reexecutar a exploração, baixe os arquivos para `data/raw/` (instruções no início do notebook) e rode `make explore`.

## Andamento

| Fase | Status |
| --- | --- |
| 1. Exploração e decisões | ✅ |
| 2. Esqueleto e CI | ✅ |
| 3. Ingestão, validação da execução e Bronze | ⏳ |
| 4. Contrato e validação de entrada | ⏳ |
| 5. dbt | ⏳ |
| 6. FastAPI | ⏳ |
| 7. Dashboard ECharts e relatório | ⏳ |
| 8. Automação e vitrine | ⏳ |

## Estrutura

```
src/cwbdatasiac/      código do pipeline (CLI typer, logging estruturado)
tests/                testes pytest
notebooks/            exploração da fonte
docs/                 demanda, plano e decisões (ADRs)
data/, logs/          gerados localmente, fora do git
```
