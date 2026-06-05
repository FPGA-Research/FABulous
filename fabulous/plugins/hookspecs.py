"""Hook specifications for the FABulous plugin system."""

from typing import Protocol

import pluggy
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
def fabulous_register_commands() -> CommandSet | list[CommandSet] | None:
    """Return a cmd2 `CommandSet` (or list of them) to add to the shell.

    The caller registers the returned command set(s) on the current shell
    instance; a hookimpl never needs a reference to the shell itself.

    Returns
    -------
    CommandSet | list[CommandSet] | None
        Command set(s) contributed by the plugin.
    """


@hookspec
def fabulous_register_code_generators() -> list[CodeGeneratorProvider]:
    """Return `list[CodeGeneratorProvider]` keyed by `HDLType`.

    Returns
    -------
    list[CodeGeneratorProvider]
        Code-generator providers contributed by the plugin.
    """


@hookspec
def fabulous_register_parsers() -> list[ParserProvider]:
    """Return `list[ParserProvider]` keyed by file suffix.

    Returns
    -------
    list[ParserProvider]
        Fabric-file parser providers contributed by the plugin.
    """


@hookspec
def fabulous_register_pnr_models() -> list[PnRModelProvider]:
    """Return `list[PnRModelProvider]` keyed by place-and-route tool name.

    Returns
    -------
    list[PnRModelProvider]
        Place-and-route model backends contributed by the plugin.
    """


@hookspec
def fabulous_after_fabric_loaded(api: FABulous_API) -> None:
    """Fire at the end of `loadFabric`; `api.fabric` is populated.

    Parameters
    ----------
    api : FABulous_API
        The API whose fabric was just loaded.
    """


@hookspec
def fabulous_register_settings() -> type[PluginSettings] | None:
    """Return a ``PluginSettings`` subclass describing plugin-owned settings.

    Returns
    -------
    type[PluginSettings] | None
        The settings model class, or ``None`` if the plugin has no settings.
    """


class FABulousHookRelay(Protocol):
    """Static type for `PluginManager.hook`, one method per hookspec above.

    `pluggy.PluginManager.hook` is a `pluggy.HookRelay`, which type-checks
    any attribute access as a `pluggy.HookCaller` whose `__call__` returns
    `Any`. `PluginManager` casts `pm.hook` to this `Protocol` so call sites
    get the real per-hook parameter and return types instead. Each method's
    return type is `list[...]` because a hook call aggregates one result per
    registered implementation.
    """

    def fabulous_startup(self) -> list[None]:
        """See `fabulous_startup`."""

    def fabulous_register_commands(
        self,
    ) -> list[CommandSet | list[CommandSet] | None]:
        """See `fabulous_register_commands`."""

    def fabulous_register_code_generators(
        self,
    ) -> list[list[CodeGeneratorProvider]]:
        """See `fabulous_register_code_generators`."""

    def fabulous_register_parsers(self) -> list[list[ParserProvider]]:
        """See `fabulous_register_parsers`."""

    def fabulous_register_pnr_models(self) -> list[list[PnRModelProvider]]:
        """See `fabulous_register_pnr_models`."""

    def fabulous_after_fabric_loaded(self, *, api: FABulous_API) -> list[None]:
        """See `fabulous_after_fabric_loaded`."""

    def fabulous_register_settings(self) -> list[type[PluginSettings] | None]:
        """See `fabulous_register_settings`."""
