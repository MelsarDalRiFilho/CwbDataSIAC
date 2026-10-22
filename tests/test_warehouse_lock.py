import subprocess
import sys
import time

import duckdb
import pytest
from dbt.cli.main import dbtRunnerResult

from cwbdatasiac import transform
from cwbdatasiac.ingestion import control
from cwbdatasiac.warehouse_lock import is_lock_error, retry_on_lock

LOCK = duckdb.IOException('IO Error: Could not set lock on file "w.duckdb"')


def _flaky(failures: int, exc: Exception = LOCK):
    calls = []

    def fn():
        calls.append(1)
        if len(calls) <= failures:
            raise exc
        return "ok"

    return fn, calls


def test_is_lock_error():
    assert is_lock_error(LOCK)
    # O dbt embrulha o erro do DuckDB: vale a mensagem, não o tipo.
    assert is_lock_error(RuntimeError(f"Runtime Error\n  {LOCK}"))
    assert not is_lock_error(duckdb.IOException("IO Error: disco cheio"))
    assert not is_lock_error(None)


def test_retries_until_lock_is_free():
    fn, calls = _flaky(failures=3)

    assert retry_on_lock(fn, max_wait_s=0.03) == "ok"
    assert len(calls) == 4


def test_other_errors_are_not_retried():
    fn, calls = _flaky(failures=1, exc=duckdb.IOException("IO Error: disco cheio"))

    with pytest.raises(duckdb.IOException, match="disco cheio"):
        retry_on_lock(fn)
    assert len(calls) == 1


def test_gives_up_after_timeout():
    fn, _ = _flaky(failures=10_000)

    with pytest.raises(duckdb.IOException, match="Could not set lock"):
        retry_on_lock(fn, timeout_s=0.2, max_wait_s=0.03)


def test_control_connect_waits_for_reader_in_other_process(tmp_path):
    path = tmp_path / "warehouse.duckdb"
    control.connect(path).close()
    reader = subprocess.Popen(
        [
            sys.executable,
            "-c",
            "import duckdb, sys, time; c = duckdb.connect(sys.argv[1], read_only=True); "
            "print('ok', flush=True); time.sleep(1); c.close()",
            str(path),
        ],
        stdout=subprocess.PIPE,
    )
    reader.stdout.readline()  # o leitor já segura o arquivo
    started = time.monotonic()
    try:
        with control.connect(path) as con:
            assert con.execute("select 1").fetchone() == (1,)
        assert time.monotonic() - started >= 0.5  # esperou o leitor soltar
    finally:
        reader.kill()
        reader.wait()


class _FakeRunner:
    def __init__(self, results):
        self.results = iter(results)

    def __call__(self):
        return self

    def invoke(self, args):
        return next(self.results)


def test_run_dbt_retries_when_dbt_cannot_lock(tmp_path, monkeypatch):
    wrapped = RuntimeError(f"Runtime Error\n  {LOCK}")
    results = [
        dbtRunnerResult(success=False, exception=LOCK),
        dbtRunnerResult(success=False, exception=wrapped),
        dbtRunnerResult(success=True),
    ]
    monkeypatch.setattr(transform, "dbtRunner", _FakeRunner(results))

    assert transform.run_dbt(["build"], tmp_path)


def test_run_dbt_does_not_retry_other_failures(tmp_path, monkeypatch):
    runner = _FakeRunner([dbtRunnerResult(success=False, exception=RuntimeError("sql"))])
    monkeypatch.setattr(transform, "dbtRunner", runner)

    assert not transform.run_dbt(["build"], tmp_path)


def test_run_dbt_reports_failure_when_lock_never_frees(tmp_path, monkeypatch):
    lock_failure = dbtRunnerResult(success=False, exception=LOCK)
    monkeypatch.setattr(transform, "dbtRunner", _FakeRunner([lock_failure] * 10_000))
    monkeypatch.setattr(
        transform, "retry_on_lock", lambda fn: retry_on_lock(fn, timeout_s=0.1, max_wait_s=0.02)
    )

    assert not transform.run_dbt(["build"], tmp_path)
