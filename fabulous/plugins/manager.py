"""The FABulous plugin manager: discovery authority, registries, and operations.

The manager is the single authority over plugins. It discovers and registers
them, folds their contributions into typed registries, builds writers and
parsers through factory methods, and owns the plugin-management operations
(list/info/install/uninstall). Plugin management is therefore *not*
itself a plugin.
"""

import importlib
import importlib.metadata as importlib_metadata
import importlib.util
import subprocess
import sys
from collections.abc import Callable, Iterable
from enum import StrEnum
from functools import partial
from pathlib import Path
from typing import Protocol, Self, TypeVar, cast

import pluggy
from cmd2 import CommandSet
from loguru import logger
from uv import find_uv_bin

from fabulous.fabric_definition.define import HDLType
from fabulous.fabric_definition.fabric import Fabric
from fabulous.fabric_generator.code_generator.code_generator import CodeGenerator
from fabulous.fabulous_api import FABulous_API
from fabulous.fabulous_settings import (
    PluginSettings,
    get_context,
)
from fabulous.plugins.hookspecs import FABulousHookRelay
from fabulous.plugins.types import (
    CodeGeneratorProvider,
    ParserProvider,
    PluginError,
    PnRModelProvider,
)


class BuiltinPlugin(StrEnum):
    """Dotted module paths of the essential built-in provider plugins.

    Each value is a real importable module exposing ``@hookimpl`` functions.
    Built-ins are always registered.
    """

    CODE_GENERATORS = "fabulous.fabric_generator.code_generator.plugin"
    PARSERS = "fabulous.fabric_generator.parser.plugin"
    PNR_MODELS = "fabulous.fabric_cad.plugin"


ESSENTIAL_PLUGINS = frozenset(BuiltinPlugin)


class _NamedProvider(Protocol):
    """Any provider descriptor: it carries a `name` for diagnostics."""

    name: str


_KeyT = TypeVar("_KeyT")
_ProviderT = TypeVar("_ProviderT", bound=_NamedProvider)


class PluginManager:
    """Owns plugin discovery, lifecycle, the provider registries, and operations."""

    pm: pluggy.PluginManager
    hook: FABulousHookRelay
    _code_generators: dict[HDLType, CodeGeneratorProvider]
    _parsers: dict[str, ParserProvider]
    _pnr_models: dict[str, PnRModelProvider]
    skip_broken: bool

    def __init__(self, skip_broken: bool = False) -> None:
        # Imported here, not at module level: hookspecs imports PluginManager
        # for its `fabulous_startup` annotation, so importing it back at
        # manager.py's top level would cycle.
        from fabulous.plugins import hookspecs

        self.pm = pluggy.PluginManager("fabulous")
        self.pm.add_hookspecs(hookspecs)
        self.hook = cast("hookspecs.FABulousHookRelay", self.pm.hook)
        self._code_generators: dict[HDLType, CodeGeneratorProvider] = {}
        self._parsers: dict[str, ParserProvider] = {}
        self._pnr_models: dict[str, PnRModelProvider] = {}
        # Resolved once by `create` so the post-discovery hooks fired through
        # this manager honour the same policy discovery ran under.
        self.skip_broken = skip_broken

    # -- Registry construction ------------------------------------------------

    def _plugin_version(self, name: str) -> str:
        """Best-effort resolve the version backing a registered plugin.

        Tier-1 built-ins are versioned with FABulous itself, and tier-3
        entry-point plugins are versioned with their distribution. Tier-2/4
        plugins are loaded from bare paths, but the path may still belong to
        an installed package, so this falls back to the module's own
        `__version__` attribute, then to `importlib.metadata` by
        registration name or by the module's top-level distribution.

        Parameters
        ----------
        name : str
            The plugin's registration name.

        Returns
        -------
        str
            The resolved version string, or ``"unknown"`` if none applies.
        """
        if name in ESSENTIAL_PLUGINS:
            return importlib_metadata.version("FABulous-FPGA")

        for ep in importlib_metadata.entry_points(group="fabulous.plugins"):
            if ep.name == name:
                return ep.dist.version if ep.dist is not None else "unknown"

        plugin = self.pm.get_plugin(name)

        version = getattr(plugin, "__version__", None)
        if version is not None:
            return str(version)

        try:
            return importlib_metadata.version(name)
        except importlib_metadata.PackageNotFoundError:
            pass

        module_name = getattr(plugin, "__name__", None)
        top_level = module_name.partition(".")[0] if module_name else None
        for dist_name in importlib_metadata.packages_distributions().get(top_level, ()):
            try:
                return importlib_metadata.version(dist_name)
            except importlib_metadata.PackageNotFoundError:
                continue

        return "unknown"

    def get_installed_plugins_str(self) -> str:
        """Build a tabular list of all registered plugins.

        Returns
        -------
        str
            A human-readable table showing plugin names, tier (core or
            plugin), and version.
        """
        header = f"  {'name':50s} {'tier':6s} version"
        status = [
            (
                name,
                "core" if name in ESSENTIAL_PLUGINS else "plugin",
                self._plugin_version(name),
            )
            for name, _ in sorted(self.pm.list_name_plugin(), key=lambda kv: kv[0])
        ]
        rows = [f"  {s[0]:50s} {s[1]:6s} {s[2]}" for s in status]
        return "Plugins:\n" + header + "\n" + "\n".join(rows)

    def get_plugin_info_str(self, name: str) -> str:
        """Build a detailed information string for a single plugin.

        Parameters
        ----------
        name : str
            The plugin name to look up.

        Returns
        -------
        str
            Multi-line string showing the plugin's tier and settings information.

        Raises
        ------
        PluginError
            If no plugin with the given name is registered.
        """
        if self.pm.get_plugin(name) is None:
            raise PluginError(f"No plugin named '{name}'")
        lines = [
            f"Plugin: {name}",
            f"  tier: {'core' if name in ESSENTIAL_PLUGINS else 'plugin'}",
            f"  version: {self._plugin_version(name)}",
        ]

        plugin = self.pm.get_plugin(name)
        register = getattr(plugin, "fabulous_register_settings", None)

        if register is None:
            lines.append("  settings: (none)")
            return "\n".join(lines)
        model = register()
        if model is None:
            lines.append("  settings: (none)")
            return "\n".join(lines)

        prefix = model.model_config.get("env_prefix", "")
        summary = f"{model.group} (env prefix {prefix})"

        if summary is not None:
            lines.append(f"  settings: {summary}")
        return "\n".join(lines)

    def _call_hook_or_skip(
        self, hook_caller: Callable[[], list], hook_name: str, skip_broken: bool
    ) -> list:
        """Invoke an aggregating hook, honouring `skip_broken` on failure.

        Pluggy calls every registered implementation of a hook in one pass, so
        a broken implementation fails the whole call; this cannot isolate
        which single plugin raised. With `skip_broken`, the hook's entire
        contribution for this call is dropped and a warning is logged instead
        of aborting.

        Parameters
        ----------
        hook_caller : Callable[[], list]
            The bound hook (e.g. `self.hook.fabulous_register_parsers`).
        hook_name : str
            The hook's name, for the warning/error message.
        skip_broken : bool
            Whether to warn and continue instead of aborting on failure.

        Returns
        -------
        list
            The hook's aggregated results, or `[]` if it failed and
            `skip_broken` is True.

        Raises
        ------
        PluginError
            If the hook call fails and `skip_broken` is False.
        """
        try:
            return hook_caller()
        except Exception as exc:  # noqa: BLE001 - policy decides re-raise
            if skip_broken:
                logger.warning(f"Skipping broken '{hook_name}' registration: {exc}")
                return []
            raise PluginError(
                f"A plugin's '{hook_name}' hook failed: {exc}\n"
                "Re-run with --skip-broken-plugins to continue past it."
            ) from exc

    def _fold_registry(
        self,
        hook_caller: Callable[[], list],
        hook_name: str,
        key: Callable[[_ProviderT], _KeyT],
        describe: Callable[[_ProviderT], str],
        skip_broken: bool,
    ) -> dict[_KeyT, _ProviderT]:
        """Fold one aggregating provider hook into a key-to-provider registry.

        Every provider hook has the same shape: it aggregates one list of
        providers per plugin, each provider claims a unique key, and a second
        plugin claiming a taken key is a conflict. This collapses that shape.

        Parameters
        ----------
        hook_caller : Callable[[], list]
            The bound hook (e.g. `self.hook.fabulous_register_parsers`).
        hook_name : str
            The hook's name, for the warning/error message.
        key : Callable[[_ProviderT], _KeyT]
            Returns the registry key a provider claims.
        describe : Callable[[_ProviderT], str]
            Returns the leading phrase naming a provider's key, used in the
            conflict message (e.g. `"Parser suffix '.csv'"`).
        skip_broken : bool
            Whether to warn and continue instead of aborting on failure.

        Returns
        -------
        dict[_KeyT, _ProviderT]
            The providers keyed by `key`.

        Raises
        ------
        PluginError
            If two providers claim the same key.
        """
        registry: dict[_KeyT, _ProviderT] = {}
        for providers in self._call_hook_or_skip(hook_caller, hook_name, skip_broken):
            for provider in providers:
                existing = registry.get(key(provider))
                if existing is not None:
                    raise PluginError(
                        f"{describe(provider)} registered by both "
                        f"'{existing.name}' and '{provider.name}'"
                    )
                registry[key(provider)] = provider
        return registry

    def build_registries(self, skip_broken: bool = False) -> None:
        """Fold the aggregating hooks into keyed registries and settings.

        Parameters
        ----------
        skip_broken : bool
            Whether to warn and continue instead of aborting when a hook
            implementation raises.

        Raises
        ------
        PluginError
            If two providers claim the same HDL type, file suffix, or
            place-and-route tool, if two plugins register settings under the
            same group, or if a hook implementation raises and `skip_broken`
            is False.
        """
        self._code_generators = self._fold_registry(
            self.hook.fabulous_register_code_generators,
            "fabulous_register_code_generators",
            key=lambda p: p.hdl_type,
            describe=lambda p: f"HDLType {p.hdl_type.name}",
            skip_broken=skip_broken,
        )
        self._parsers = self._fold_registry(
            self.hook.fabulous_register_parsers,
            "fabulous_register_parsers",
            key=lambda p: p.suffix,
            describe=lambda p: f"Parser suffix '{p.suffix}'",
            skip_broken=skip_broken,
        )
        self._pnr_models = self._fold_registry(
            self.hook.fabulous_register_pnr_models,
            "fabulous_register_pnr_models",
            key=lambda p: p.tool,
            describe=lambda p: f"Place-and-route tool '{p.tool}'",
            skip_broken=skip_broken,
        )

        # build settings
        settings_results = self._call_hook_or_skip(
            self.hook.fabulous_register_settings,
            "fabulous_register_settings",
            skip_broken,
        )
        new_settings: dict[str, PluginSettings] = {}
        for model in settings_results:
            if model is None:
                continue
            if model.group in new_settings:
                raise PluginError(
                    f"Settings group '{model.group}' registered more than once"
                )
            new_settings[model.group] = model()

        store = get_context().plugin_settings
        store.clear()
        store.update(new_settings)

    # -- Factory methods (the only resolution surface consumers touch) --------

    def make_writer(self, hdl_type: HDLType) -> CodeGenerator:
        """Build a fresh code generator for `hdl_type`.

        This is the single resolution point for writers: it selects the
        registered provider and constructs the generator. A provider needing
        configuration reads it from its own `PluginSettings.from_context()`,
        so callers never thread options through here.

        Parameters
        ----------
        hdl_type : HDLType
            The HDL language to build a generator for.

        Returns
        -------
        CodeGenerator
            A fresh generator instance.

        Raises
        ------
        PluginError
            If no provider is registered for `hdl_type`.
        """
        provider = self._code_generators.get(hdl_type)
        if provider is None:
            available = ", ".join(sorted(h.value for h in self._code_generators))
            raise PluginError(
                f"No code generator registered for '{hdl_type.value}'. "
                f"Available: {available or '(none)'}"
            )
        return provider.factory()

    def make_parser(self, path: Path) -> Callable[[Path], Fabric]:
        """Return the parse callable that handles ``path`` by its suffix.

        Parameters
        ----------
        path : Path
            The fabric file whose suffix selects the parser.

        Returns
        -------
        Callable[[Path], Fabric]
            The parse callable from the registered provider.

        Raises
        ------
        PluginError
            If no parser is registered for the file's suffix.
        """
        provider = self._parsers.get(path.suffix)
        if provider is None:
            available = ", ".join(sorted(self._parsers))
            raise PluginError(
                f"No parser registered for suffix '{path.suffix}'. "
                f"Available: {available or '(none)'}"
            )
        return provider.parse

    def make_pnr_model(
        self, tool: str | None = None, timed: bool = False
    ) -> PnRModelProvider:
        """Return the place-and-route model provider for `tool`.

        Parameters
        ----------
        tool : str | None
            The place-and-route tool to model. Defaults to None, which
            selects the project's `pnr_backend` setting.
        timed : bool
            Whether the caller intends to supply a delay model. Defaults to
            False. A backend that cannot consume one is rejected here rather
            than silently generating an untimed model.

        Returns
        -------
        PnRModelProvider
            The registered provider for the resolved tool.

        Raises
        ------
        PluginError
            If no provider is registered for the resolved tool, or if `timed`
            is requested from a provider that does not support timing.
        """
        tool = tool or get_context().pnr_backend
        provider = self._pnr_models.get(tool)
        if provider is None:
            available = ", ".join(sorted(self._pnr_models))
            raise PluginError(
                f"No place-and-route model registered for '{tool}'. "
                f"Available: {available or '(none)'}"
            )
        if timed and not provider.supports_timing:
            raise PluginError(
                f"Place-and-route backend '{tool}' does not support timing, "
                "so it cannot consume a delay model."
            )
        return provider

    # -- Lifecycle ------------------------------------------------------------

    def notify_startup(self) -> None:
        """Fire the one-shot startup hook for a session.

        Only a session that initialises cmd2 fires this; `create` itself does
        not, so building a manager purely to inspect or install plugins never
        runs a plugin's startup side effects.
        """
        self._call_hook_or_skip(
            self.hook.fabulous_startup, "fabulous_startup", self.skip_broken
        )

    def collect_command_sets(self) -> list[CommandSet]:
        """Gather the cmd2 command sets contributed by every plugin.

        A hookimpl may return a single `CommandSet` or a list of them; both are
        flattened here so callers register a uniform sequence.

        Returns
        -------
        list[CommandSet]
            Command sets to register on the shell, in hook-call order.
        """
        results = self._call_hook_or_skip(
            self.hook.fabulous_register_commands,
            "fabulous_register_commands",
            self.skip_broken,
        )
        command_sets = []
        for result in results:
            if result is None:
                continue
            if isinstance(result, (list, tuple)):
                command_sets.extend(result)
            else:
                command_sets.append(result)
        return command_sets

    def notify_fabric_loaded(self, api: FABulous_API) -> None:
        """Fire the post-load lifecycle hook for a freshly loaded fabric.

        Centralising the firing here keeps the manager the sole authority over
        hook dispatch, so callers never reach into the pluggy hook relay. Unlike
        `fabulous_startup` (fired once per session by `notify_startup`), this
        fires on every fabric load.

        Parameters
        ----------
        api : FABulous_API
            The API whose fabric was just loaded.
        """
        self.hook.fabulous_after_fabric_loaded(api=api)

    # -- Plugin management (owned by the manager, not a plugin) ---------------

    @property
    def installed_plugins(self) -> set[str]:
        """Return the names of the installed `fabulous.plugins` entry points.

        Returns
        -------
        set[str]
            Entry-point names currently registered in the `fabulous.plugins`
            group for the running interpreter.
        """
        importlib.invalidate_caches()
        return {
            ep.name for ep in importlib_metadata.entry_points(group="fabulous.plugins")
        }

    def install(self, spec: str) -> tuple[bool, str]:
        """Install a plugin package into the running environment via uv.

        Parameters
        ----------
        spec : str
            A uv/pip install specifier (package name, git URL, or local path).

        Returns
        -------
        tuple[bool, str]
            Whether the package added a new `fabulous.plugins` entry point,
            and a human-readable summary of the result.
        """
        before = self.installed_plugins
        subprocess.run(
            [find_uv_bin(), "pip", "install", "--python", sys.executable, spec],
            check=True,
        )
        added = sorted(self.installed_plugins - before)
        if added:
            return True, f"Installed. Added plugin(s): {', '.join(added)}."
        return False, (
            "Installed, but no new plugin entry points appeared. This "
            "usually means the package was already installed; uv installs "
            "the latest matching version by default, so re-running this "
            "command against an already-installed spec updates it in "
            "place. Check the resulting version with `fabulous plugins "
            "info <name>`."
        )

    def uninstall(self, name: str) -> tuple[bool, str]:
        """Uninstall a plugin package via uv.

        Parameters
        ----------
        name : str
            The package name to uninstall.

        Returns
        -------
        tuple[bool, str]
            Whether any `fabulous.plugins` entry points were removed, and a
            human-readable summary of the result.
        """
        before = self.installed_plugins
        subprocess.run(
            [find_uv_bin(), "pip", "uninstall", "--python", sys.executable, name],
            check=True,
        )
        removed = sorted(before - self.installed_plugins)
        return bool(removed), f"Uninstalled. Removed plugin(s): {', '.join(removed)}."

    # -- Discovery tiers ------------------------------------------------------

    @staticmethod
    def _load_path_module(name: str, init: Path) -> object:
        """Import a plugin module from an `__init__.py` (or module) file.

        Parameters
        ----------
        name : str
            The module name to import under.
        init : Path
            Path to the `__init__.py` or module file to load.

        Returns
        -------
        object
            The imported module.

        Raises
        ------
        PluginError
            If the path cannot be resolved to an importable module.
        """
        spec = importlib.util.spec_from_file_location(name, init)
        if spec is None or spec.loader is None:
            raise PluginError(f"'{init}' is not an importable Python module")
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return module

    def _register_external(
        self, name: str, load: Callable[[], object], skip_broken: bool
    ) -> None:
        """Load, version-check, and register one externally discovered plugin.

        Tiers 2-4 are the untrusted boundary, so each plugin must declare a
        compatible contract version through a module-level ``FABULOUS_PLUGIN_API``
        attribute. A load failure, a version mismatch, or a registration clash
        is routed through :meth:`_handle_broken`, honouring ``skip_broken``.

        Parameters
        ----------
        name : str
            The registration name for the plugin.
        load : Callable[[], object]
            Zero-argument callable returning the imported plugin module.
        skip_broken : bool
            Whether to warn and continue instead of aborting on failure.

        Raises
        ------
        PluginError
            If the plugin fails to load, version-check, or register and
            ``skip_broken`` is False.
        """
        try:
            self._load_and_register_plugin(name, load)
        except Exception as exc:  # noqa: BLE001 - policy decides re-raise
            if skip_broken:
                logger.warning(f"Skipping broken plugin '{name}': {exc}")
                return
            raise PluginError(
                f"Plugin '{name}' failed to load: {exc}\n"
                "Re-run with --skip-broken-plugins to continue past it."
            ) from exc

    def _load_and_register_plugin(self, name: str, load: Callable[[], object]) -> None:
        """Load and register a single plugin after version validation.

        Parameters
        ----------
        name : str
            The registration name for the plugin.
        load : Callable[[], object]
            Zero-argument callable returning the imported plugin module.

        Raises
        ------
        PluginError
            If the plugin API version is incompatible.
        """
        from fabulous.plugins.hookspecs import PLUGIN_API_VERSION

        module = load()
        declared = getattr(module, "FABULOUS_PLUGIN_API", None)
        if declared != PLUGIN_API_VERSION:
            raise PluginError(
                f"declares plugin API {declared!r}, but this FABulous provides "
                f"{PLUGIN_API_VERSION}; set FABULOUS_PLUGIN_API = "
                f"{PLUGIN_API_VERSION} once the plugin supports it"
            )
        self.pm.register(module, name=name)

    # -- Construction helpers -------------------------------------------------

    @classmethod
    def core_only(cls) -> Self:
        """Build a manager with only the essential built-ins registered.

        Returns
        -------
        Self
            A manager with tier-1 plugins registered and registries built.
        """
        manager = cls()
        for plugin in BuiltinPlugin:
            module = importlib.import_module(plugin.value)
            manager.pm.register(module, name=plugin.value)
        manager.build_registries()
        return manager

    @classmethod
    def create(
        cls, extra_plugins: Iterable[str] = (), skip_broken: bool | None = None
    ) -> Self:
        """Build a fully discovered manager across all tiers.

        Parameters
        ----------
        extra_plugins : Iterable[str], optional
            Tier-4 session plugins (`-m/--plugin` values).
        skip_broken : bool | None
            Override for `skip_broken_plugins`; `None` uses the setting.

        Returns
        -------
        Self
            The populated manager, with every tier discovered and the
            registries built. Firing `fabulous_startup` is the caller's
            job, through `notify_startup`.
        """
        if skip_broken is None:
            skip_broken = get_context().skip_broken_plugins

        manager = cls(skip_broken=skip_broken)

        # Register tier-1 built-in plugins. These are always present and essential.
        for plugin in BuiltinPlugin:
            module = importlib.import_module(plugin.value)
            manager.pm.register(module, name=plugin.value)

        # Discover tier-2 sub-plugins from the project plugin directory
        plugin_dir = get_context().plugin_dir
        if not plugin_dir.is_absolute():
            plugin_dir = get_context().proj_dir / plugin_dir

        if plugin_dir.is_dir():
            for child in sorted(plugin_dir.iterdir(), key=lambda p: p.name):
                init = child / "__init__.py"
                if not child.is_dir() or not init.exists():
                    continue
                name = child.name
                manager._register_external(
                    name, partial(manager._load_path_module, name, init), skip_broken
                )

        # Register tier-3 entry-point plugins. The `importlib_metadata` API returns
        eps = sorted(
            importlib_metadata.entry_points(group="fabulous.plugins"),
            key=lambda ep: ep.name,
        )
        for ep in eps:
            manager._register_external(ep.name, ep.load, skip_broken)

        # Register tier-4 session plugins.
        for spec in extra_plugins:
            path = Path(spec)
            if path.exists():
                if path.is_dir():
                    name = path.name
                    init = path / "__init__.py"
                    if not init.exists():

                        def _missing_init(init: Path = init) -> object:
                            raise PluginError(
                                f"No '__init__.py' found in plugin directory "
                                f"'{init.parent}'"
                            )

                        manager._register_external(name, _missing_init, skip_broken)
                        continue
                else:
                    name = path.stem
                    init = path
                load = partial(manager._load_path_module, name, init)
            else:
                name = spec
                load = partial(importlib.import_module, spec)
            manager._register_external(name, load, skip_broken)

        manager.build_registries(skip_broken=skip_broken)
        return manager
