# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project status

Data-engineering portfolio project over Curitiba's open data (SIAC 156 citizen requests). Requirements live in `docs/data_siac_demanda.md`; the phased plan (and the source of truth for architecture/stack decisions) is `docs/data_siac_plano.md`. Phases 1 (exploration: `notebooks/00_exploracao.ipynb`, `docs/adr/0001-chave-e-historico-das-solicitacoes.md`) and 2 (skeleton + CI) are done. Docs, comments and log messages are written in Portuguese.

## Environment

- Python **3.12** (`.python-version`, `requires-python >=3.12`), managed with **uv**; package lives in `src/cwbdatasiac/` (hatchling build), CLI entry point `cwbdatasiac` (typer).
- Dependency groups: `dev` (default: ruff, pytest, pytest-cov, pre-commit) and `explore` (notebook deps, opt-in via `--group explore`).
- Raw data is downloaded to `data/raw/` (git-ignored) from the C3SL mirror `http://dadosabertos.c3sl.ufpr.br/curitiba/156/` (manifest: `156.xml`).

## Commands

```bash
make install                          # uv sync + pre-commit hooks
make check                            # what CI runs: ruff check, ruff format --check, pytest
make format                           # ruff autofix + format
uv run pytest tests/test_cli.py::test_version   # single test
make explore                          # re-execute the exploration notebook (needs data/raw/)
```

pytest always runs with coverage and fails below 80% (`[tool.coverage.report]` in `pyproject.toml`). Ruff excludes `notebooks/`.

## Logging convention

Call `configure_logging()` once (the CLI callback does it); wrap each pipeline execution in `run_context()` so every record carries the same `run_id`. Use `logging.getLogger(__name__)` and pass structured fields via `extra={...}` — they become top-level JSON keys. Logs go to stderr and `logs/cwbdatasiac.log` (rotating).

## Source data facts that drive the design

- Each daily CSV is a **cumulative snapshot of the current year**, UTF-8 **with BOM**, CRLF, `;` separator, trailing `;` producing an empty unnamed last column.
- Dates are `dd/mm/yyyy` with **no time component**.
- There is **no request identifier**, and ~39k fully identical rows are legitimate distinct requests — never deduplicate. Per-request SCD2 is not feasible; history is kept as aggregated counts per snapshot (ADR 0001).
- `Logradouro` holds street addresses: publish only aggregates (LGPD).
