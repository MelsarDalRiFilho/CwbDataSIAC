# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project status

Data-engineering portfolio project over Curitiba's open data (SIAC 156 citizen requests). Requirements live in `docs/data_siac_demanda.md`; the phased plan (and the source of truth for architecture/stack decisions) is `docs/data_siac_plano.md`. Phase 1 (exploration) is done: `notebooks/00_exploracao.ipynb` and `docs/adr/0001-chave-e-historico-das-solicitacoes.md`. No application code yet. Docs are written in Portuguese.

## Environment

- Python **3.12** (`.python-version`, `requires-python >=3.12`), managed with **uv**.
- Dependency group `explore` holds notebook deps (duckdb, pandas, pyarrow, jupyter, openpyxl).
- Raw data is downloaded to `data/raw/` (git-ignored) from the C3SL mirror `http://dadosabertos.c3sl.ufpr.br/curitiba/156/` (manifest: `156.xml`).

## Commands

```bash
uv sync --group explore                                                       # create/update .venv
uv run jupyter nbconvert --to notebook --execute --inplace notebooks/00_exploracao.ipynb   # re-run exploration
```

No test runner or linter is configured yet (planned for phase 2: ruff, pytest, pytest-cov).

## Source data facts that drive the design

- Each daily CSV is a **cumulative snapshot of the current year**, UTF-8 **with BOM**, CRLF, `;` separator, trailing `;` producing an empty unnamed last column.
- Dates are `dd/mm/yyyy` with **no time component**.
- There is **no request identifier**, and ~39k fully identical rows are legitimate distinct requests — never deduplicate. Per-request SCD2 is not feasible; history is kept as aggregated counts per snapshot (ADR 0001).
- `Logradouro` holds street addresses: publish only aggregates (LGPD).
