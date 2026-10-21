.PHONY: install lint format test check explore

install:  ## instala dependências e os hooks de pre-commit
	uv sync
	uv run pre-commit install

lint:
	uv run ruff check .
	uv run ruff format --check .

format:
	uv run ruff check --fix .
	uv run ruff format .

test:
	uv run pytest

check: lint test  ## o mesmo que o CI roda

explore:  ## reexecuta o notebook de exploração (precisa de data/raw/)
	uv run --group explore jupyter nbconvert --to notebook --execute --inplace notebooks/00_exploracao.ipynb
