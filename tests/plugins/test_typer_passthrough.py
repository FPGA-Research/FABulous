"""The top-level `FABulous plugins` group shares the management operations."""

from pytest_mock import MockerFixture
from typer.testing import CliRunner

from fabulous import fabulous as entry

runner = CliRunner()


def test_plugins_list_runs(mocker: MockerFixture) -> None:
    mocker.patch.object(
        entry.FABulousPluginManager, "core_only", return_value="MANAGER"
    )
    fmt = mocker.patch(
        "fabulous.plugins.management.format_plugin_list", return_value="LISTING"
    )
    result = runner.invoke(entry.plugins_app, ["list"])
    assert result.exit_code == 0
    assert "LISTING" in result.stdout
    fmt.assert_called_once_with("MANAGER")


def test_plugins_install_runs(mocker: MockerFixture) -> None:
    install = mocker.patch("fabulous.plugins.management.install_plugin")
    result = runner.invoke(entry.plugins_app, ["install", "some-pkg"])
    assert result.exit_code == 0
    install.assert_called_once_with("some-pkg")
