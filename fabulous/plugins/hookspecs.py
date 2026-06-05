"""Hook specifications for the FABulous plugin system.

All hooks use the ``fabulous_`` prefix and are collect-from-all (no
``firstresult``). Heavy argument types are referenced as string forward-refs so
this module stays free of import cycles; pluggy never evaluates the annotations.
"""

from typing import TYPE_CHECKING

import pluggy

if TYPE_CHECKING:
    from cmd2 import CommandSet

    from fabulous.fabulous_api import FABulous_API
    from fabulous.fabulous_cli import FABulous_CLI
    from fabulous.plugins.manager import FABulousPluginManager
    from fabulous.plugins.types import (
        CodeGeneratorProvider,
        ParserProvider,
        PluginSettingsSpec,
    )

hookspec = pluggy.HookspecMarker("fabulous")
hookimpl = pluggy.HookimplMarker("fabulous")


@hookspec
def fabulous_startup(manager: "FABulousPluginManager") -> None:
    """Run once after all plugins are registered, before the shell loop.

    Parameters
    ----------
    manager : FABulousPluginManager
        The fully populated plugin manager.
    """


@hookspec
def fabulous_register_commands(
    cli: "FABulous_CLI",
) -> "CommandSet | list[CommandSet] | None":
    """Return a cmd2 ``CommandSet`` (or list of them) to add to the shell.

    Parameters
    ----------
    cli : FABulous_CLI
        The shell instance the command set will be registered on.

    Returns
    -------
    CommandSet | list[CommandSet] | None
        Command set(s) contributed by the plugin.
    """


@hookspec
def fabulous_register_code_generators() -> "list[CodeGeneratorProvider]":
    """Return ``list[CodeGeneratorProvider]`` keyed by ``HDLType``.

    Returns
    -------
    list[CodeGeneratorProvider]
        Code-generator providers contributed by the plugin.
    """


@hookspec
def fabulous_register_parsers() -> "list[ParserProvider]":
    """Return ``list[ParserProvider]`` keyed by file suffix.

    Returns
    -------
    list[ParserProvider]
        Fabric-file parser providers contributed by the plugin.
    """


@hookspec
def fabulous_after_fabric_loaded(api: "FABulous_API") -> None:
    """Fire at the end of ``loadFabric``; ``api.fabric`` is populated.

    Parameters
    ----------
    api : FABulous_API
        The API whose fabric was just loaded.
    """


@hookspec
def fabulous_register_settings() -> "PluginSettingsSpec | None":
    """Return a ``PluginSettingsSpec`` describing plugin-owned settings.

    Returns
    -------
    PluginSettingsSpec | None
        The settings spec, or ``None`` if the plugin has no settings.
    """
