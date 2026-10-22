"""Espera pelo lock de escrita do warehouse.

A API abre o DuckDB em modo leitura a cada requisição (milissegundos). Enquanto
alguma leitura está aberta, o DuckDB recusa escritores de outro processo com
"Could not set lock". Sob tráfego contínuo, a maioria das tentativas de escrita
cai nessa janela, então a ingestão e o dbt tentam de novo, com espera curta e
aleatória, até `timeout_s`.
"""

import logging
from collections.abc import Callable

from tenacity import Retrying, retry_if_exception, stop_after_delay, wait_random

LOCK_MESSAGE = "Could not set lock"
LOCK_TIMEOUT_S = 60.0

log = logging.getLogger(__name__)


def is_lock_error(exc: BaseException | None) -> bool:
    # Pela mensagem, não pelo tipo: o dbt embrulha o IOException do DuckDB em DbtRuntimeError.
    return exc is not None and LOCK_MESSAGE in str(exc)


def retry_on_lock[T](
    fn: Callable[[], T], *, timeout_s: float = LOCK_TIMEOUT_S, max_wait_s: float = 0.5
) -> T:
    """Executa `fn`, repetindo enquanto ela falhar por lock do warehouse."""
    retrying = Retrying(
        stop=stop_after_delay(timeout_s),
        wait=wait_random(0.02, max_wait_s),
        retry=retry_if_exception(is_lock_error),
        reraise=True,
    )
    result = retrying(fn)
    if (attempts := retrying.statistics["attempt_number"]) > 1:
        log.info("lock do warehouse obtido após espera", extra={"tentativas": attempts})
    return result
