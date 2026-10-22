"""CLI do pipeline."""

from datetime import date, datetime
from pathlib import Path
from typing import Annotated

import httpx
import typer

from cwbdatasiac import __version__
from cwbdatasiac.config import IngestSettings
from cwbdatasiac.ingestion.pipeline import run_ingestion
from cwbdatasiac.observability import configure_logging
from cwbdatasiac.transform import run_dbt

app = typer.Typer(help="Pipeline de dados abertos do SIAC 156 de Curitiba.", no_args_is_help=True)

USER_AGENT = f"cwbdatasiac/{__version__} (+https://github.com/MelsarDalRiFilho/CwbDataSIAC)"


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


def _parse_date(value: str | None) -> date | None:
    return datetime.strptime(value, "%Y-%m-%d").date() if value else None


@app.command()
def ingest(
    data: Annotated[
        str | None,
        typer.Option(help="Data do snapshot (AAAA-MM-DD). Padrão: o mais recente."),
    ] = None,
    forcar: Annotated[bool, typer.Option(help="Recarrega mesmo se já carregado.")] = False,
    data_dir: Annotated[Path, typer.Option(help="Diretório de dados.")] = Path("data"),
    min_bytes: Annotated[int, typer.Option(help="Tamanho mínimo aceito do CSV.")] = 50_000_000,
    manter_csv_dias: Annotated[int, typer.Option(help="CSVs brutos mantidos em raw/.")] = 3,
    navegador: Annotated[
        bool, typer.Option(help="Usa o Playwright como último recurso de descoberta.")
    ] = True,
    tolerancia_contrato: Annotated[
        float,
        typer.Option(
            min=0.0, max=1.0, help="Fração máxima de linhas que violam regras bloqueantes."
        ),
    ] = 0.001,
) -> None:
    """Baixa o snapshot do SIAC 156, valida e grava na camada Bronze."""
    settings = IngestSettings(
        data_dir=data_dir,
        min_bytes=min_bytes,
        keep_raw_days=manter_csv_dias,
        use_browser=navegador,
        contract_tolerance=tolerancia_contrato,
    )
    with httpx.Client(
        timeout=settings.timeout_s, follow_redirects=True, headers={"User-Agent": USER_AGENT}
    ) as client:
        execucao = run_ingestion(settings, client, _parse_date(data), force=forcar)

    typer.echo(f"{execucao.status}: {execucao.arquivo or '-'} ({execucao.run_id})")
    if execucao.status == "falha":
        typer.echo(f"etapa {execucao.etapa_falha}: {execucao.mensagem}", err=True)
        raise typer.Exit(code=1)


@app.command()
def transform(
    data_dir: Annotated[Path, typer.Option(help="Diretório de dados.")] = Path("data"),
    full_refresh: Annotated[
        bool, typer.Option(help="Reconstrói o histórico agregado do zero.")
    ] = False,
) -> None:
    """Roda `dbt build` (seeds, modelos e testes) sobre a camada Bronze."""
    if not run_dbt(["build", *(["--full-refresh"] if full_refresh else [])], data_dir):
        raise typer.Exit(code=1)


@app.command()
def docs(
    data_dir: Annotated[Path, typer.Option(help="Diretório de dados.")] = Path("data"),
) -> None:
    """Gera a documentação e a linhagem do dbt (dbt/siac156/target/static_index.html)."""
    if not run_dbt(["docs", "generate", "--static"], data_dir):
        raise typer.Exit(code=1)
