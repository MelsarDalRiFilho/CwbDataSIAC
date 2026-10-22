.PHONY: install install-browser lint format test check ingest transform docs pipeline api report site explore

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

transform:  ## dbt build: seeds, modelos e testes sobre a Bronze
	uv run cwbdatasiac transform

docs:  ## documentação e linhagem do dbt em dbt/siac156/target/static_index.html
	uv run cwbdatasiac docs

pipeline: ingest transform  ## ingestão seguida do dbt

api:  ## sobe a API em http://127.0.0.1:8000 (painel em /painel, docs em /docs)
	uv run cwbdatasiac api

report:  ## relatório analítico em reports/relatorio.html
	uv run cwbdatasiac report

site: docs  ## site estático em site/ (o que vai para o GitHub Pages)
	uv run cwbdatasiac site

explore:  ## reexecuta o notebook de exploração (precisa de data/raw/)
	uv run --group explore jupyter nbconvert --to notebook --execute --inplace notebooks/00_exploracao.ipynb
