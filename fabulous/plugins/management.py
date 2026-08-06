"""The `plugins` command surface shared by the shell and the Typer entry.

This is *not* a plugin. The manager owns every operation; these helpers only
format the manager's state, and the `PluginCommands` set is a thin cmd2 bridge
that the CLI registers directly. The shell subcommands (`plugins list`,
`plugins info`, …) use cmd2's `with_annotated`, so each subparser is built from
the handler's type-annotated signature instead of a hand-rolled parser.
"""

from collections.abc import Callable
from typing import Annotated, ClassVar

import cmd2
from cmd2 import CommandSet
from cmd2.annotated import Argument

from fabulous.plugins.manager import PluginManager


class PluginCommands(CommandSet):
    """The shell ``plugins ...`` surface (a thin bridge to the manager)."""

    DEFAULT_CATEGORY: ClassVar[str] = "Plugins"

    @property
    def _manager(self) -> PluginManager:
        """Access the FABulous plugin manager from the parent cmd2 instance."""
        return self._cmd.plugin_manager

    @cmd2.with_annotated(base_command=True, subcommand_required=False)
    def do_plugins(self, cmd2_subcommand_func: Callable[[], None] | None) -> None:
        """Manage FABulous plugins (falls back to help without a subcommand)."""
        if cmd2_subcommand_func is not None:
            cmd2_subcommand_func()
        else:
            self._cmd.do_help("plugins")

    @cmd2.with_annotated(subcommand_to="plugins", help="List discovered plugins")
    def plugins_list(self) -> None:
        """List discovered plugins."""
        self._cmd.poutput(self._manager.get_installed_plugins_str())

    @cmd2.with_annotated(subcommand_to="plugins", help="Show plugin detail")
    def plugins_info(
        self, name: Annotated[str, Argument(help_text="Plugin name")]
    ) -> None:
        """Show detail for a single plugin."""
        self._cmd.poutput(self._manager.get_plugin_info_str(name))

    @cmd2.with_annotated(
        subcommand_to="plugins", help="Install a plugin package via uv"
    )
    def plugins_install(
        self,
        spec: Annotated[
            str, Argument(help_text="Package name, git URL, or local path")
        ],
    ) -> None:
        """Install a plugin package via uv."""
        _, message = self._manager.install(spec)
        self._cmd.poutput(message)

    @cmd2.with_annotated(
        subcommand_to="plugins", help="Uninstall a plugin package via uv"
    )
    def plugins_uninstall(
        self, name: Annotated[str, Argument(help_text="Package name")]
    ) -> None:
        """Uninstall a plugin package via uv."""
        _, message = self._manager.uninstall(name)
        self._cmd.poutput(message)
