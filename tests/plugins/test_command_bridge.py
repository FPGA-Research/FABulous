"""A plugin-contributed CommandSet appears in the shell with its category."""

import types
from pathlib import Path

from cmd2 import CommandSet, with_default_category

from fabulous.fabulous_cli import FABulous_CLI
from fabulous.fabulous_settings import init_context
from fabulous.plugins import hookspecs
from fabulous.plugins.manager import FABulousPluginManager


@with_default_category("Demo")
class _DemoCommands(CommandSet):
    def do_demo_ping(self, _statement: object) -> None:
        self._cmd.poutput("pong")


def test_plugin_command_registered(project: Path) -> None:
    init_context(project)
    manager = FABulousPluginManager.core_only()

    demo_module = types.ModuleType("demo_cmd_plugin")

    @hookspecs.hookimpl
    def fabulous_register_commands() -> CommandSet:
        return _DemoCommands()

    demo_module.fabulous_register_commands = fabulous_register_commands
    manager.pm.register(demo_module, name="demo")

    cli = FABulous_CLI("verilog", plugin_manager=manager, interactive=False)
    assert "demo_ping" in cli.get_all_commands()
