.PHONY: install install-browser lint format test check ingest explore

install:  ## instala dependências e os hooks de pre-commit
	uv sync
	uv run pre-commit install

install-browser:  ## extra opcional: Playwright para a descoberta pelo navegador
	uv sync --extra browser
	uv run playwright install chromium

lint:
	uv run ruff check .
	uv run ruff format --check .

format:
	uv run ruff check --fix .
	uv run ruff format .

test:
	uv run pytest

check: lint test  ## o mesmo que o CI roda

ingest:  ## baixa o snapshot mais recente, valida e grava no Bronze (idempotente)
	uv run cwbdatasiac ingest

explore:  ## reexecuta o notebook de exploração (precisa de data/raw/)
	uv run --group explore jupyter nbconvert --to notebook --execute --inplace notebooks/00_exploracao.ipynb
