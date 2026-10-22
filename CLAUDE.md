# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project status

Data-engineering portfolio project over Curitiba's open data (SIAC 156 citizen requests). Requirements live in `docs/data_siac_demanda.md`; the phased plan (and the source of truth for architecture/stack decisions) is `docs/data_siac_plano.md`. Phases 1 (exploration: `notebooks/00_exploracao.ipynb`, `docs/adr/0001-chave-e-historico-das-solicitacoes.md`) 2 (skeleton + CI), 3 (ingestion → Bronze), 4 (Pandera input contract), 5 (dbt models), 6 (FastAPI), 7 (ECharts dashboard, report, GitHub Pages) and 8 (daily automation, README showcase) are done — all phases of the plan. Docs, comments and log messages are written in Portuguese.

## Environment

- Python **3.12** (`.python-version`, `requires-python >=3.12`), managed with **uv**; package lives in `src/cwbdatasiac/` (hatchling build), CLI entry point `cwbdatasiac` (typer).
- Dependency groups: `dev` (default: ruff, pytest, pytest-cov, pre-commit) and `explore` (notebook deps, opt-in via `--group explore`).
- Extra `browser` (Playwright) is optional: `make install-browser`. CI never installs it.
- Everything under `data/` is git-ignored: `raw/` (last 3 CSVs), `bronze/siac156/snapshot_data=YYYY-MM-DD/part-0.parquet`, `quarentena/`, `qualidade/` (contract reports), `warehouse.duckdb`.

## Commands

```bash
make install                          # uv sync + pre-commit hooks
make check                            # what CI runs: ruff check, ruff format --check, pytest
make format                           # ruff autofix + format
uv run pytest tests/test_cli.py::test_version   # single test
make ingest                           # real ingestion of the latest snapshot (network, ~13 s)
make transform                        # dbt build over Bronze (~7 s); make docs → lineage HTML
make api                              # FastAPI on :8000 (/painel dashboard, /docs)
make site                             # docs + static site in site/ (what GitHub Pages serves)
make explore                          # re-execute the exploration notebook (needs data/raw/)
uv run pytest -m "not slow"           # skip real dbt builds and API tests (~30 s)
```

pytest always runs with coverage and fails below 80% (`[tool.coverage.report]` in `pyproject.toml`). Ruff excludes `notebooks/`. To run dbt directly: `cd dbt/siac156 && CWBDATASIAC_DATA_DIR=$PWD/../../data uv run dbt build --project-dir . --profiles-dir .`

## Ingestion architecture

`cwbdatasiac ingest` → `ingestion/pipeline.py::run_ingestion`, which never raises: every outcome becomes a `control.Execucao` row in `controle.ingestao_execucoes` (status `sucesso` | `sem_novidade` | `falha`), and the CLI maps `falha` to exit code 1. Steps raise `IngestionError` subclasses (`errors.py`) whose `etapa` is recorded and whose `quarantine` flag moves the downloaded CSV to `data/quarentena/`. Discovery (`discovery.py`) tries strategies in order — C3SL manifest, portal JSON endpoint, Playwright (`browser.py`) — and logs a warning per failed strategy. Before writing Bronze, `validation/contracts.py::validate` runs two Pandera schemas on the Arrow table: *blocking* rules (required columns, date format/range, answer ≥ creation, column dtype) and *alert* rules (known domains). Blocking violations only reject the snapshot when the fraction of invalid rows exceeds `contract_tolerance` (default 0.001) — or always, for dtype errors; rows are never dropped. Violations are persisted to `controle.contrato_violacoes` and a JSON report; examples are restricted to the rule's columns and never include `Logradouro`. DuckDB connections are opened briefly per read/write so the warehouse file is not locked during downloads.

Tests never hit the network: `respx` mocks httpx, and `tests/conftest.py::make_csv` builds synthetic CSVs in the source format (BOM, CRLF, trailing `;`). Don't commit real rows (they contain addresses).

## dbt architecture

`cwbdatasiac transform` → `transform.py::run_dbt`, which invokes `dbtRunner` on `dbt/siac156` with `CWBDATASIAC_DATA_DIR` set to the absolute data dir; `profiles.yml` (warehouse path) and `_sources.yml` (Bronze `external_location` via `read_parquet(..., hive_partitioning = false)`) read it. A custom `generate_schema_name` makes schemas plain `staging`/`intermediate`/`marts`/`seeds`. Marts read only the latest snapshot (`int_solicitacoes__ultimo_snapshot`), except dimensions and the incremental `fct_snapshot_agregado` (delete+insert by `snapshot_data`), which scan all snapshots. Data tests live on marts, not on staging, so build time does not grow with history. Integrity tests are `error`; quality rules the contract already tolerates are `warn`. The staging unit test uses `format: sql` for the source because an external Parquet source has no relation for dbt to introspect. dbt-duckdb keeps the DuckDB file open in-process after a run — open it with the same config (not `read_only`) in the same process.

## API and warehouse concurrency

`api/main.py::create_app(data_dir)` (module-level `app` reads `CWBDATASIAC_DATA_DIR`) serves marts and `controle` tables. `api/db.py::Warehouse.query` opens a **read-only DuckDB connection per query** and closes it; a `duckdb.IOException` (locked or missing file) becomes `WarehouseUnavailable` → 503 with `Retry-After`. DuckDB forbids readers in other processes while a writer holds the file and vice versa, so every **writer** goes through `warehouse_lock.py::retry_on_lock` (control.connect and `transform._invoke_waiting_for_lock`); lock errors are detected by message because dbt wraps the DuckDB exception. Never expose `logradouro` from the API. Routers build SQL only from fixed fragments; user input is always a bound parameter. API tests (`tests/api/`) build a real warehouse once per session by running dbt in a **subprocess** (in-process dbt would keep the file open and block read-only connections).

## Dashboard, report and site

`dashboard/` is plain HTML/CSS/JS (ECharts 6 from jsDelivr), served by the API at `/painel` and copied into `site/` for GitHub Pages. `js/app.js` detects the mode: if `data/manifest.json` exists it reads `data/<key>.json`, otherwise it calls the API routes in its `SOURCES` map. That map **must stay identical** to `cwbdatasiac.site.SOURCES` (enforced by `tests/api/test_site.py`). `site.collect` produces the JSON by calling the API in-process (TestClient), so both modes see the same shapes; `/solicitacoes` is never exported (Pages gets aggregates only). `report/` renders `templates/relatorio.html.j2` with findings computed from the same data — write findings so they stay true when data changes (and when small datasets trigger fallbacks). Charts follow the dataviz skill's reference palette (CSS custom properties, light + dark), single-series charts have no legend, every chart has a table view, numbers are formatted pt-BR. Render and screenshot (Playwright is in the `browser` extra) after visual changes — several bugs here were only visible on screen. `.github/workflows/pages.yml` ("Atualização diária", cron 09:30 UTC + manual) restores the Bronze from the `dados` GitHub release (`cwbdatasiac historico importar`; one `bronze_siac156_YYYY-MM-DD.parquet` asset per snapshot), runs ingest → transform → docs → pytest → site (+ `scripts/coverage_badge.py` → `site/badges/coverage.json` for the shields.io endpoint badge), uploads new snapshots (`historico exportar`), deploys Pages, and opens/comments/closes the `atualizacao-diaria` issue. The warehouse is only cached (derived data; dbt rebuilds it from Bronze). `docs/img/painel.gif` (README) must stay under 1 MB (pre-commit `check-added-large-files`).

## Logging convention

Call `configure_logging()` once (the CLI callback does it); wrap each pipeline execution in `run_context()` so every record carries the same `run_id`. Use `logging.getLogger(__name__)` and pass structured fields via `extra={...}` — they become top-level JSON keys. Logs go to stderr and `logs/cwbdatasiac.log` (rotating).

## Source data facts that drive the design

- Each daily CSV is a **cumulative snapshot of the current year**, UTF-8 **with BOM**, CRLF, `;` separator, trailing `;` producing an empty unnamed last column.
- Dates are `dd/mm/yyyy` with **no time component**.
- There is **no request identifier**, and ~39k fully identical rows are legitimate distinct requests — never deduplicate. Per-request SCD2 is not feasible; history is kept as aggregated counts per snapshot (ADR 0001).
- `Logradouro` holds street addresses: publish only aggregates (LGPD).
