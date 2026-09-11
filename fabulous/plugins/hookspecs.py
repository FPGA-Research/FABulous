"""Hook specifications for the FABulous plugin system.

Pluggy binds hook arguments by name and never evaluates annotations, so every
type named below is imported for type checking only. That keeps
`from fabulous.plugins import hookimpl` cheap for a plugin author, who would
otherwise pay for the whole generator stack to reach a marker.
"""

from typing import TYPE_CHECKING

import pluggy

if TYPE_CHECKING:
    from cmd2 import CommandSet

    from fabulous.fabulous_api import FABulous_API
    from fabulous.fabulous_settings import PluginSettings
    from fabulous.plugins.types import (
        CodeGeneratorProvider,
        ParserProvider,
        PnRModelProvider,
    )

hookspec = pluggy.HookspecMarker("fabulous")
hookimpl = pluggy.HookimplMarker("fabulous")


PLUGIN_API_VERSION = 1
"""Version of the plugin-hook contract.

Bump this on any backwards-incompatible change to the hook specifications below.
Externally discovered plugins (the directory, entry-point, and session tiers)
must declare the version they target through a module-level
`FABULOUS_PLUGIN_API` attribute; discovery rejects any plugin whose declared
version does not match this one.
"""


@hookspec
def fabulous_startup() -> None:
    """Run once after all plugins are registered, before cmd2 initialisation."""


@hookspec
def fabulous_register_commands() -> "CommandSet | list[CommandSet] | None":
    """Return a cmd2 `CommandSet` (or list of them) to add to the shell.

    The caller registers the returned command set(s) on the current shell
    instance; a hookimpl never needs a reference to the shell itself.

    Returns
    -------
    CommandSet | list[CommandSet] | None
        Command set(s) contributed by the plugin.
    """


@hookspec
def fabulous_register_code_generators() -> "list[CodeGeneratorProvider]":
    """Return `list[CodeGeneratorProvider]` keyed by `HDLType`.

    Returns
    -------
    list[CodeGeneratorProvider]
        Code-generator providers contributed by the plugin.
    """


@hookspec
def fabulous_register_parsers() -> "list[ParserProvider]":
    """Return `list[ParserProvider]` keyed by file suffix.

    Returns
    -------
    list[ParserProvider]
        Fabric-file parser providers contributed by the plugin.
    """


@hookspec
def fabulous_register_pnr_models() -> "list[PnRModelProvider]":
    """Return `list[PnRModelProvider]` keyed by place-and-route tool name.

    Returns
    -------
    list[PnRModelProvider]
        Place-and-route model backends contributed by the plugin.
    """


@hookspec
def fabulous_after_fabric_loaded(api: "FABulous_API") -> None:
    """Fire at the end of `loadFabric`; `api.fabric` is populated.

    Parameters
    ----------
    api : FABulous_API
        The API whose fabric was just loaded.
    """


@hookspec
def fabulous_register_settings() -> "type[PluginSettings] | None":
    """Return a `PluginSettings` subclass describing plugin-owned settings.

    Returns
    -------
    type[PluginSettings] | None
        The settings model class, or `None` if the plugin has no settings.
    """
