"""Hook specifications for the FABulous plugin system.

Pluggy binds hook arguments by name and never evaluates annotations, so every
type named below is imported for type checking only. That keeps
`from fabulous.plugins import hookimpl` cheap for a plugin author, who would
otherwise import the whole generator stack to get the marker.
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
Directory, entry-point and session plugins must declare the version they
target through a module-level `FABULOUS_PLUGIN_API` attribute; discovery
rejects any plugin whose declared version does not match this one.
"""


@hookspec
def fabulous_startup() -> None:
    """Run once after all plugins are registered, before cmd2 initialisation."""


@hookspec
def fabulous_register_commands() -> "CommandSet | list[CommandSet] | None":
    """Contribute a cmd2 `CommandSet`, or a list of them, to the shell.

    The shell registers whatever is returned on itself, so a hookimpl never
    needs a reference to the shell instance.

    Returns
    -------
    CommandSet | list[CommandSet] | None
        Command set(s) contributed by the plugin.
    """


@hookspec
def fabulous_register_code_generators() -> "list[CodeGeneratorProvider]":
    """Contribute code generators, each claiming one `HDLType`.

    Returns
    -------
    list[CodeGeneratorProvider]
        Code-generator providers contributed by the plugin.
    """


@hookspec
def fabulous_register_parsers() -> "list[ParserProvider]":
    """Contribute fabric-file parsers, each claiming one file suffix.

    Returns
    -------
    list[ParserProvider]
        Fabric-file parser providers contributed by the plugin.
    """


@hookspec
def fabulous_register_pnr_models() -> "list[PnRModelProvider]":
    """Contribute place-and-route model backends, each claiming one tool name.

    Returns
    -------
    list[PnRModelProvider]
        Place-and-route model backends contributed by the plugin.
    """


@hookspec
def fabulous_after_fabric_loaded(api: "FABulous_API") -> None:
    """Run after every fabric load, once `api.fabric` is populated.

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
