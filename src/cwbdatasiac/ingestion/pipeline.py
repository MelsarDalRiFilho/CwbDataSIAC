"""Orquestra a ingestão: descoberta → download → checagens → Bronze → controle.

Cada execução tem um `run_id`, aparece no log e numa linha de
`controle.ingestao_execucoes`. Falhas não levantam exceção: viram status
`falha` com a etapa e o motivo, e o CLI traduz isso em exit code ≠ 0.
"""

import logging
import shutil
from datetime import UTC, date, datetime

import httpx
import pyarrow as pa

from cwbdatasiac.config import IngestSettings
from cwbdatasiac.ingestion import bronze, checks, control
from cwbdatasiac.ingestion.discovery import FILE_NAME_RE, Strategy, default_strategies, discover
from cwbdatasiac.ingestion.download import download
from cwbdatasiac.ingestion.errors import CheckError, IngestionError
from cwbdatasiac.observability import run_context

log = logging.getLogger(__name__)


def _save(settings: IngestSettings, execucao: control.Execucao) -> None:
    # Conexões curtas: o arquivo do DuckDB não fica travado durante o download.
    with control.connect(settings.warehouse_path) as con:
        control.save(con, execucao)


def prune_raw(settings: IngestSettings) -> list[str]:
    """Mantém no `raw/` só os CSVs das `keep_raw_days` datas mais recentes."""
    dated = sorted(
        (p for p in settings.raw_dir.glob("*.csv") if FILE_NAME_RE.match(p.name)),
        key=lambda p: p.name,
        reverse=True,
    )
    removed = []
    for path in dated[settings.keep_raw_days :]:
        path.unlink()
        removed.append(path.name)
    return removed


def run_ingestion(
    settings: IngestSettings,
    client: httpx.Client,
    snapshot_date: date | None = None,
    *,
    force: bool = False,
    strategies: list[tuple[str, Strategy]] | None = None,
) -> control.Execucao:
    with run_context() as run_id:
        execucao = control.Execucao(run_id=run_id, inicio=datetime.now(UTC))
        _save(settings, execucao)
        log.info("ingestão iniciada", extra={"etapa": "inicio", "forcar": force})
        try:
            _run(settings, client, snapshot_date, force, strategies, execucao)
        except IngestionError as exc:
            _fail(settings, execucao, exc.etapa, str(exc), exc.quarantine)
        except Exception as exc:
            log.exception("erro inesperado na ingestão", extra={"etapa": "inesperado"})
            _fail(settings, execucao, "inesperado", repr(exc), quarantine=False)
        finally:
            execucao.fim = datetime.now(UTC)
            _save(settings, execucao)

        log.info(
            "ingestão finalizada",
            extra={
                "etapa": "fim",
                "status": execucao.status,
                "snapshot_data": execucao.snapshot_data,
                "linhas": execucao.linhas,
                "duracao_s": round((execucao.fim - execucao.inicio).total_seconds(), 2),
            },
        )
        return execucao


def _run(
    settings: IngestSettings,
    client: httpx.Client,
    snapshot_date: date | None,
    force: bool,
    strategies: list[tuple[str, Strategy]] | None,
    execucao: control.Execucao,
) -> None:
    remote = discover(client, snapshot_date, strategies or default_strategies(settings.use_browser))
    execucao.snapshot_data = remote.snapshot_date
    execucao.arquivo = remote.name
    execucao.url = remote.url
    execucao.fonte_descoberta = remote.source

    with control.connect(settings.warehouse_path) as con:
        already_loaded = control.success_for(con, remote.snapshot_date)
        previous = control.last_success(con, before=remote.snapshot_date)
    partition = bronze.partition_path(settings.bronze_dir, remote.snapshot_date)
    if already_loaded and partition.exists() and not force:
        execucao.status = "sem_novidade"
        execucao.mensagem = "snapshot já carregado; use --forcar para recarregar"
        return

    result = download(
        client,
        remote,
        settings.raw_dir,
        attempts=settings.retry_attempts,
        wait_s=settings.retry_wait_s,
    )
    execucao.bytes = result.bytes
    execucao.sha256 = result.sha256

    checks.check_content(result, settings.min_bytes)
    checks.check_header(result.path)
    if previous and previous[2] == result.sha256 and not force:
        result.path.unlink()
        execucao.status = "sem_novidade"
        execucao.mensagem = f"conteúdo idêntico ao snapshot de {previous[0]}"
        log.warning("fonte não atualizou o conteúdo", extra={"etapa": "integridade"})
        return

    try:
        table = bronze.read_csv(result.path)
    except pa.ArrowInvalid as exc:
        raise CheckError("leitura", f"CSV malformado: {exc}") from exc
    execucao.linhas = table.num_rows
    checks.check_volume(table.num_rows, remote.snapshot_date, previous and previous[:2])

    path = bronze.write_bronze(table, settings.bronze_dir, remote.snapshot_date)
    log.info(
        "partição bronze gravada",
        extra={"etapa": "bronze", "caminho": str(path), "linhas": table.num_rows},
    )
    execucao.status = "sucesso"

    if removed := prune_raw(settings):
        log.info("CSVs antigos removidos do raw", extra={"etapa": "retencao", "arquivos": removed})


def _fail(
    settings: IngestSettings,
    execucao: control.Execucao,
    etapa: str,
    message: str,
    quarantine: bool,
) -> None:
    execucao.status = "falha"
    execucao.etapa_falha = etapa
    execucao.mensagem = message
    log.error("ingestão falhou", extra={"etapa": etapa, "motivo": message})

    if quarantine and execucao.arquivo:
        source = settings.raw_dir / execucao.arquivo
        if source.exists():
            settings.quarantine_dir.mkdir(parents=True, exist_ok=True)
            dest = settings.quarantine_dir / f"{execucao.run_id}_{execucao.arquivo}"
            shutil.move(source, dest)
            log.warning(
                "arquivo enviado para a quarentena", extra={"etapa": etapa, "destino": str(dest)}
            )
