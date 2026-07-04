from idm_cli.cli import app
from typer.testing import CliRunner

runner = CliRunner()

def test_cli_help():
    result = runner.invoke(app, ["--help"])
    assert result.exit_code == 0
    assert "Usage:" in result.stdout or "Options:" in result.stdout
