"""CLI do pipeline. Os comandos de ingestão, transformação etc. entram nas próximas fases."""

from pathlib import Path
from typing import Annotated

import typer

from cwbdatasiac import __version__
from cwbdatasiac.observability import configure_logging

app = typer.Typer(help="Pipeline de dados abertos do SIAC 156 de Curitiba.", no_args_is_help=True)


@app.callback()
def main(
    log_level: Annotated[str, typer.Option(help="Nível de log.")] = "INFO",
    log_dir: Annotated[Path, typer.Option(help="Diretório do arquivo de log.")] = Path("logs"),
) -> None:
    configure_logging(log_level, log_dir)


@app.command()
def version() -> None:
    """Mostra a versão instalada."""
    typer.echo(__version__)
