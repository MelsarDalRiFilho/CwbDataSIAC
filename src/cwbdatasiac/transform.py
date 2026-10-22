"""Executa o projeto dbt (`dbt/siac156`) sobre o warehouse do diretório de dados.

O projeto lê a Bronze e grava no `warehouse.duckdb` do mesmo diretório; o caminho
chega ao `profiles.yml` e ao `_sources.yml` pela variável CWBDATASIAC_DATA_DIR.
"""

import logging
import os
from pathlib import Path

from dbt.cli.main import dbtRunner

from cwbdatasiac.observability import run_context

DBT_PROJECT_DIR = Path(__file__).resolve().parents[2] / "dbt" / "siac156"
DATA_DIR_ENV = "CWBDATASIAC_DATA_DIR"

log = logging.getLogger(__name__)


def run_dbt(command: list[str], data_dir: Path, extra_args: list[str] | None = None) -> bool:
    """Roda um comando do dbt (ex.: ["build"]) e retorna se teve sucesso."""
    args = [
        *command,
        "--project-dir",
        str(DBT_PROJECT_DIR),
        "--profiles-dir",
        str(DBT_PROJECT_DIR),
        *(extra_args or []),
    ]
    previous = os.environ.get(DATA_DIR_ENV)
    os.environ[DATA_DIR_ENV] = str(data_dir.resolve())
    try:
        with run_context():
            log.info("dbt iniciado", extra={"etapa": "dbt", "comando": " ".join(command)})
            result = dbtRunner().invoke(args)
            if result.success:
                log.info("dbt concluído", extra={"etapa": "dbt", "comando": " ".join(command)})
            else:
                log.error(
                    "dbt falhou",
                    extra={
                        "etapa": "dbt",
                        "comando": " ".join(command),
                        "erro": repr(result.exception),
                    },
                )
            return result.success
    finally:
        if previous is None:
            os.environ.pop(DATA_DIR_ENV, None)
        else:
            os.environ[DATA_DIR_ENV] = previous
