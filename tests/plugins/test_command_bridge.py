"""A plugin-contributed CommandSet appears in the shell with its category."""

import io
from pathlib import Path
from typing import ClassVar

from cmd2 import CommandSet
from pytest_mock import MockerFixture

from fabulous.fabulous_repl.fabulous_repl import FABulousREPL
from fabulous.fabulous_settings import init_context
from fabulous.plugins import hookspecs
from fabulous.plugins.manager import BuiltinPlugin, PluginManager
from tests.conftest import run_cmd


class _DemoCommands(CommandSet):
    DEFAULT_CATEGORY: ClassVar[str] = "Demo"

    def do_demo_ping(self, _statement: object) -> None:
        self._cmd.poutput("pong")


class _DemoCommandsPlugin:
    @hookspecs.hookimpl
    def fabulous_register_commands(self) -> CommandSet:
        return _DemoCommands()


def test_plugin_command_registered(project: Path, mocker: MockerFixture) -> None:
    init_context(project)
    manager = PluginManager.core_only()
    manager.pm.register(_DemoCommandsPlugin(), name="demo")
    mocker.patch.object(PluginManager, "create", return_value=manager)

    cli = FABulousREPL("verilog", interactive=False)
    assert "demo_ping" in cli.get_all_commands()
    assert cli.tcl.eval("info commands demo_ping") == "demo_ping"
    assert cli.tcl.eval("info commands plugins") == "plugins"


def _plugins_cli(project: Path, mocker: MockerFixture) -> FABulousREPL:
    """A non-interactive shell with the built-in `plugins` command set."""
    init_context(project)
    manager = PluginManager.core_only()
    mocker.patch.object(PluginManager, "create", return_value=manager)
    return FABulousREPL("verilog", interactive=False)


def test_plugins_info_subcommand_reports_the_plugin(
    project: Path, mocker: MockerFixture
) -> None:
    cli = _plugins_cli(project, mocker)
    cli.stdout = io.StringIO()

    run_cmd(cli, f"plugins info {BuiltinPlugin.PARSERS.value}")

    assert f"Plugin: {BuiltinPlugin.PARSERS.value}" in cli.stdout.getvalue()


def test_plugins_without_subcommand_shows_help(
    project: Path, mocker: MockerFixture
) -> None:
    cli = _plugins_cli(project, mocker)
    cli.stdout = io.StringIO()

    run_cmd(cli, "plugins")

    assert "list" in cli.stdout.getvalue()
