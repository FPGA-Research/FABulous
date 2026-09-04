"""The top-level `FABulous plugins` group shares the management operations."""

from pathlib import Path

import pytest
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


def test_plugins_group_skips_project_validation(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The `plugins` group runs without a scaffolded FABulous project.

    Outside a project there is no `.FABulous` to validate against, so the
    context is built in `api_mode` and the group still lists its built-ins.
    """
    monkeypatch.chdir(tmp_path)

    result = runner.invoke(entry.app, ["plugins", "list"], catch_exceptions=False)

    assert result.exit_code == 0
    assert "fabulous.fabric_generator.parser.plugin" in result.stdout


def test_plugins_group_honours_explicit_project_dir(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """`--project-dir` must reach discovery, not be silently dropped.

    The project holds a tier-2 sub-plugin, which only appears in the listing
    if discovery ran against the passed directory rather than the cwd.
    """
    (tmp_path / ".FABulous").mkdir()
    plugin_dir = tmp_path / "plugins" / "demo_plug"
    plugin_dir.mkdir(parents=True)
    (plugin_dir / "__init__.py").write_text(
        "from fabulous.plugins import PLUGIN_API_VERSION\n"
        "FABULOUS_PLUGIN_API = PLUGIN_API_VERSION\n"
    )
    monkeypatch.chdir(tmp_path.parent)

    result = runner.invoke(
        entry.app,
        ["--project-dir", str(tmp_path), "plugins", "list"],
        catch_exceptions=False,
    )

    assert result.exit_code == 0
    assert "demo_plug" in result.stdout
