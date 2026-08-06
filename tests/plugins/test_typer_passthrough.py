"""The top-level `FABulous plugins` group shares the management operations."""

from pathlib import Path

from pytest_mock import MockerFixture
from typer.testing import CliRunner

from fabulous import fabulous as entry

runner = CliRunner()


def test_plugins_list_runs(mocker: MockerFixture) -> None:
    fmt = mocker.patch.object(
        entry.PluginManager, "get_installed_plugins_str", return_value="LISTING"
    )
    result = runner.invoke(entry.plugins_app, ["list"])
    assert result.exit_code == 0
    assert "LISTING" in result.stdout
    fmt.assert_called_once()


def test_plugins_install_runs(mocker: MockerFixture) -> None:
    install = mocker.patch.object(
        entry.PluginManager,
        "install",
        return_value=(True, "Installed. Added plugin(s): demo."),
    )
    result = runner.invoke(entry.plugins_app, ["install", "some-pkg"])
    assert result.exit_code == 0
    assert "demo" in result.stdout
    install.assert_called_once_with("some-pkg")


def test_plugins_group_skips_project_validation(mocker: MockerFixture) -> None:
    """The `plugins` group runs without a scaffolded FABulous project.

    It still initialises the context (so an explicit `--project-dir` reaches
    plugin discovery), but in `api_mode`, which skips the `.FABulous`
    validation that a real project directory would otherwise require.
    """
    init = mocker.patch.object(entry, "init_context")
    mocker.patch.object(
        entry.PluginManager, "get_installed_plugins_str", return_value="LISTING"
    )

    result = runner.invoke(entry.app, ["plugins", "list"])

    assert result.exit_code == 0
    init.assert_called_once_with(project_dir=None, api_mode=True)


def test_plugins_group_honours_explicit_project_dir(
    tmp_path: Path, mocker: MockerFixture
) -> None:
    """`--project-dir` must reach plugin discovery, not be silently dropped."""
    (tmp_path / ".FABulous").mkdir()
    init = mocker.patch.object(entry, "init_context")
    mocker.patch.object(
        entry.PluginManager, "get_installed_plugins_str", return_value="LISTING"
    )

    result = runner.invoke(
        entry.app, ["--project-dir", str(tmp_path), "plugins", "list"]
    )

    assert result.exit_code == 0
    init.assert_called_once_with(project_dir=tmp_path.resolve(), api_mode=True)
