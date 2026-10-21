from typer.testing import CliRunner

from cwbdatasiac import __version__
from cwbdatasiac.cli import app

runner = CliRunner()


def test_version(tmp_path):
    result = runner.invoke(app, ["--log-dir", str(tmp_path), "version"])

    assert result.exit_code == 0
    assert result.stdout.strip() == __version__


def test_callback_creates_log_dir(tmp_path):
    log_dir = tmp_path / "logs"
    runner.invoke(app, ["--log-dir", str(log_dir), "version"])

    assert log_dir.is_dir()
