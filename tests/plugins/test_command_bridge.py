"""A plugin-contributed CommandSet appears in the shell with its category."""

import io
import types
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


def test_plugin_command_registered(project: Path, mocker: MockerFixture) -> None:
    init_context(project)
    manager = PluginManager.core_only()

    demo_module = types.ModuleType("demo_cmd_plugin")

    @hookspecs.hookimpl
    def fabulous_register_commands() -> CommandSet:
        return _DemoCommands()

    demo_module.fabulous_register_commands = fabulous_register_commands
    manager.pm.register(demo_module, name="demo")
    mocker.patch.object(PluginManager, "create", return_value=manager)

    cli = FABulousREPL("verilog", interactive=False)
    assert "demo_ping" in cli.get_all_commands()


def _plugins_cli(project: Path, mocker: MockerFixture) -> FABulousREPL:
    """A non-interactive shell with the built-in ``plugins`` command set."""
    init_context(project)
    manager = PluginManager.core_only()
    mocker.patch.object(PluginManager, "create", return_value=manager)
    return FABulousREPL("verilog", interactive=False)


def test_plugins_list_subcommand_dispatches(
    project: Path, mocker: MockerFixture
) -> None:
    cli = _plugins_cli(project, mocker)
    fmt = mocker.patch.object(
        PluginManager, "get_installed_plugins_str", return_value="LISTING"
    )

    run_cmd(cli, "plugins list")

    fmt.assert_called_once()  # cmd2 routed `plugins list` to the _list handler


def test_plugins_info_subcommand_passes_argument(
    project: Path, mocker: MockerFixture
) -> None:
    cli = _plugins_cli(project, mocker)
    fmt = mocker.patch.object(PluginManager, "get_plugin_info_str", return_value="INFO")

    run_cmd(cli, f"plugins info {BuiltinPlugin.PARSERS.value}")

    fmt.assert_called_once()
    # the positional `name` was parsed and forwarded to the handler
    assert fmt.call_args.args[0] == BuiltinPlugin.PARSERS.value


def test_plugins_without_subcommand_shows_help(
    project: Path, mocker: MockerFixture
) -> None:
    cli = _plugins_cli(project, mocker)
    cli.stdout = io.StringIO()

    run_cmd(cli, "plugins")

    # the no-subcommand branch falls back to help, which lists the subcommands
    assert "list" in cli.stdout.getvalue()
