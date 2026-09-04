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
from typing import Protocol, Self, TypeVar

import pluggy
from cmd2 import CommandSet
from loguru import logger
from uv import find_uv_bin

from fabulous.custom_exception import PluginError
from fabulous.fabric_definition.define import HDLType
from fabulous.fabric_definition.fabric import Fabric
from fabulous.fabric_generator.code_generator.code_generator import CodeGenerator
from fabulous.fabulous_api import FABulous_API
from fabulous.fabulous_settings import (
    PluginSettings,
    get_context,
)
from fabulous.plugins import hookspecs
from fabulous.plugins.hookspecs import PLUGIN_API_VERSION
from fabulous.plugins.types import (
    CodeGeneratorProvider,
    ParserProvider,
    PnRModelProvider,
)

PLUGIN_ENTRY_POINT_GROUP = "fabulous.plugins"


class BuiltinPlugin(StrEnum):
    """Dotted module paths of the essential built-in provider plugins.

    Each value is a real importable module exposing `@hookimpl` functions.
    Built-ins are always registered.
    """

    CODE_GENERATORS = "fabulous.fabric_generator.code_generator.plugin"
    PARSERS = "fabulous.fabric_generator.parser.plugin"
    PNR_MODELS = "fabulous.fabric_cad.plugin"


class _NamedProvider(Protocol):
    """Any provider descriptor: it carries a `name` for diagnostics."""

    name: str


_KeyT = TypeVar("_KeyT")
_ProviderT = TypeVar("_ProviderT", bound=_NamedProvider)


class PluginManager:
    """Owns plugin discovery, lifecycle, the provider registries, and operations."""

    pm: pluggy.PluginManager
    _code_generators: dict[HDLType, CodeGeneratorProvider]
    _parsers: dict[str, ParserProvider]
    _pnr_models: dict[str, PnRModelProvider]
    skip_broken: bool
    _top_level_distributions: dict[str, list[str]] | None

    def __init__(self, skip_broken: bool = False) -> None:
        self.pm = pluggy.PluginManager("fabulous")
        self.pm.add_hookspecs(hookspecs)
        self._code_generators: dict[HDLType, CodeGeneratorProvider] = {}
        self._parsers: dict[str, ParserProvider] = {}
        self._pnr_models: dict[str, PnRModelProvider] = {}
        # Resolved once by `create` so the post-discovery hooks fired through
        # this manager honour the same policy discovery ran under.
        self.skip_broken = skip_broken
        self._top_level_distributions = None

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
            The resolved version string, or `"unknown"` if none applies.
        """
        if name in BuiltinPlugin:
            return importlib_metadata.version("FABulous-FPGA")

        for ep in importlib_metadata.entry_points(
            group=PLUGIN_ENTRY_POINT_GROUP, name=name
        ):
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
        if self._top_level_distributions is None:
            self._top_level_distributions = importlib_metadata.packages_distributions()
        for dist_name in self._top_level_distributions.get(top_level, ()):
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
                "core" if name in BuiltinPlugin else "plugin",
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
            f"  tier: {'core' if name in BuiltinPlugin else 'plugin'}",
            f"  version: {self._plugin_version(name)}",
        ]

        # Read the settings hookimpl out of pluggy's registry rather than off
        # the module, so a hookimpl registered under a different function name
        # through `@hookimpl(specname=...)` is still found.
        model = next(
            (
                impl.function()
                for impl in self.pm.hook.fabulous_register_settings.get_hookimpls()
                if impl.plugin_name == name
            ),
            None,
        )
        if model is None:
            lines.append("  settings: (none)")
        else:
            prefix = model.model_config.get("env_prefix", "")
            lines.append(f"  settings: {model.group} (env prefix {prefix})")
        return "\n".join(lines)

    def _call_hook_or_skip(
        self, hook_caller: pluggy.HookCaller, **kwargs: object
    ) -> list:
        """Invoke an aggregating hook one implementation at a time.

        Calling the hook relay would run every implementation in one pass, so a
        single raising plugin fails the whole call and takes the built-in
        providers down with it. Driving the implementations individually
        attributes a failure to its plugin, and under `skip_broken` unregisters
        only that plugin so the later hooks no longer see it.

        Parameters
        ----------
        hook_caller : pluggy.HookCaller
            The hook to drive, e.g. `self.pm.hook.fabulous_register_parsers`.
        **kwargs : object
            Arguments forwarded to each implementation.

        Returns
        -------
        list
            One entry per implementation that returned a result, in pluggy's
            call order.

        Raises
        ------
        PluginError
            If an implementation raises and `skip_broken` is False, or if it
            is a hook wrapper, which this call path cannot drive.
        """
        results = []
        for impl in list(hook_caller.get_hookimpls()):
            if impl.hookwrapper or impl.wrapper:
                raise PluginError(
                    f"Plugin '{impl.plugin_name}' implements "
                    f"'{hook_caller.name}' as a hook wrapper, which FABulous "
                    "does not support."
                )
            try:
                result = impl.function(**kwargs)
            except Exception as exc:  # noqa: BLE001 - policy decides re-raise
                if not self.skip_broken:
                    raise PluginError(
                        f"Plugin '{impl.plugin_name}' failed in "
                        f"'{hook_caller.name}': {exc}\n"
                        "Re-run with --skip-broken-plugins to continue past it."
                    ) from exc
                logger.warning(
                    f"Unregistering broken plugin '{impl.plugin_name}': it "
                    f"failed in '{hook_caller.name}': {exc}"
                )
                self.pm.unregister(name=impl.plugin_name)
                continue
            if result is not None:
                results.append(result)
        return results

    def _fold_registry(
        self,
        hook_caller: pluggy.HookCaller,
        key: Callable[[_ProviderT], _KeyT],
        describe: Callable[[_ProviderT], str],
    ) -> dict[_KeyT, _ProviderT]:
        """Fold one aggregating provider hook into a key-to-provider registry.

        Every provider hook has the same shape: it aggregates one list of
        providers per plugin, each provider claims a unique key, and a second
        plugin claiming a taken key is a conflict. This collapses that shape.

        Parameters
        ----------
        hook_caller : pluggy.HookCaller
            The hook to drive, e.g. `self.pm.hook.fabulous_register_parsers`.
        key : Callable[[_ProviderT], _KeyT]
            Returns the registry key a provider claims.
        describe : Callable[[_ProviderT], str]
            Returns the leading phrase naming a provider's key, used in the
            conflict message (e.g. `"Parser suffix '.csv'"`).

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
        for providers in self._call_hook_or_skip(hook_caller):
            for provider in providers:
                provider_key = key(provider)
                existing = registry.get(provider_key)
                if existing is not None:
                    raise PluginError(
                        f"{describe(provider)} registered by both "
                        f"'{existing.name}' and '{provider.name}'"
                    )
                registry[provider_key] = provider
        return registry

    def build_registries(self) -> None:
        """Fold the aggregating hooks into keyed registries and settings.

        Raises
        ------
        PluginError
            If two providers claim the same HDL type, file suffix, or
            place-and-route tool, if two plugins register settings under the
            same group, or if a hook implementation raises and `skip_broken`
            is False.
        """
        self._code_generators = self._fold_registry(
            self.pm.hook.fabulous_register_code_generators,
            key=lambda p: p.hdl_type,
            describe=lambda p: f"HDLType {p.hdl_type.name}",
        )
        self._parsers = self._fold_registry(
            self.pm.hook.fabulous_register_parsers,
            key=lambda p: p.suffix,
            describe=lambda p: f"Parser suffix '{p.suffix}'",
        )
        self._pnr_models = self._fold_registry(
            self.pm.hook.fabulous_register_pnr_models,
            key=lambda p: p.tool,
            describe=lambda p: f"Place-and-route tool '{p.tool}'",
        )

        # build settings
        new_settings: dict[str, PluginSettings] = {}
        for model in self._call_hook_or_skip(self.pm.hook.fabulous_register_settings):
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
        """Return the parse callable that handles `path` by its suffix.

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
        self._call_hook_or_skip(self.pm.hook.fabulous_startup)

    def collect_command_sets(self) -> list[CommandSet]:
        """Gather the cmd2 command sets contributed by every plugin.

        A hookimpl may return a single `CommandSet` or a list of them; both are
        flattened here so callers register a uniform sequence.

        Returns
        -------
        list[CommandSet]
            Command sets to register on the shell, in hook-call order.
        """
        command_sets = []
        for result in self._call_hook_or_skip(self.pm.hook.fabulous_register_commands):
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
        self._call_hook_or_skip(self.pm.hook.fabulous_after_fabric_loaded, api=api)

    # -- Plugin management (owned by the manager, not a plugin) ---------------

    @staticmethod
    def installed_plugins() -> set[str]:
        """Return the names of the installed `fabulous.plugins` entry points.

        Returns
        -------
        set[str]
            Entry-point names currently registered in the `fabulous.plugins`
            group for the running interpreter.
        """
        return {
            ep.name
            for ep in importlib_metadata.entry_points(group=PLUGIN_ENTRY_POINT_GROUP)
        }

    @classmethod
    def install(cls, spec: str) -> tuple[bool, str]:
        """Install a plugin package into the running environment via uv.

        Installing reads no plugin state, so this deliberately needs no
        discovered manager: a plugin already broken on this machine must not
        stop another one from being installed.

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
        before = cls.installed_plugins()
        subprocess.run(
            [find_uv_bin(), "pip", "install", "--python", sys.executable, spec],
            check=True,
        )
        # The subprocess wrote new metadata that this interpreter's import
        # caches predate.
        importlib.invalidate_caches()
        added = sorted(cls.installed_plugins() - before)
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

    @classmethod
    def uninstall(cls, name: str) -> tuple[bool, str]:
        """Uninstall a plugin package via uv.

        Like `install`, this needs no discovered manager, so a plugin that
        fails to import can still be removed.

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
        before = cls.installed_plugins()
        subprocess.run(
            [find_uv_bin(), "pip", "uninstall", "--python", sys.executable, name],
            check=True,
        )
        importlib.invalidate_caches()
        removed = sorted(before - cls.installed_plugins())
        if not removed:
            return False, (
                "Uninstalled, but no plugin entry points disappeared. The "
                "package was either not installed or is not a FABulous plugin."
            )
        return True, f"Uninstalled. Removed plugin(s): {', '.join(removed)}."

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
            If the path does not exist or cannot be resolved to an importable
            module.
        BaseException
            Whatever the plugin module itself raised while executing,
            re-raised after its `sys.modules` entry is removed.
        """
        if not init.exists():
            if init.name == "__init__.py":
                raise PluginError(
                    f"No '__init__.py' found in plugin directory '{init.parent}'"
                )
            raise PluginError(f"No plugin module found at '{init}'")
        spec = importlib.util.spec_from_file_location(name, init)
        if spec is None or spec.loader is None:
            raise PluginError(f"'{init}' is not an importable Python module")
        module = importlib.util.module_from_spec(spec)
        # A package plugin's own `from .sub import x` resolves its parent
        # through sys.modules, so the entry has to exist before execution.
        sys.modules[name] = module
        try:
            spec.loader.exec_module(module)
        except BaseException:
            del sys.modules[name]
            raise
        return module

    def _register_external(self, name: str, load: Callable[[], object]) -> None:
        """Load, version-check, and register one externally discovered plugin.

        Tiers 2-4 are the untrusted boundary, so each plugin must declare a
        compatible contract version through a module-level `FABULOUS_PLUGIN_API`
        attribute. A load failure, a version mismatch, or a registration clash
        aborts, unless `skip_broken` downgrades it to a warning.

        Parameters
        ----------
        name : str
            The registration name for the plugin.
        load : Callable[[], object]
            Zero-argument callable returning the imported plugin module.

        Raises
        ------
        PluginError
            If the plugin fails to load, version-check, or register and
            `skip_broken` is False.
        """
        try:
            self._load_and_register_plugin(name, load)
        except Exception as exc:  # noqa: BLE001 - policy decides re-raise
            if self.skip_broken:
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
            If the plugin API version is incompatible, or if it implements a
            hook this FABulous does not specify.
        """
        module = load()
        declared = getattr(module, "FABULOUS_PLUGIN_API", None)
        if declared != PLUGIN_API_VERSION:
            raise PluginError(
                f"declares plugin API {declared!r}, but this FABulous provides "
                f"{PLUGIN_API_VERSION}; set FABULOUS_PLUGIN_API = "
                f"{PLUGIN_API_VERSION} once the plugin supports it"
            )
        self.pm.register(module, name=name)
        # A hookimpl whose name matches no hookspec is inert otherwise, so a
        # misspelled hook leaves the plugin looking installed and doing nothing.
        # Only this plugin can have added pending impls, so the blame is exact.
        try:
            self.pm.check_pending()
        except pluggy.PluginValidationError as exc:
            self.pm.unregister(name=name)
            raise PluginError(str(exc)) from exc

    # -- Construction helpers -------------------------------------------------

    def _register_builtins(self) -> None:
        """Register the tier-1 built-ins, which are always present."""
        for plugin in BuiltinPlugin:
            module = importlib.import_module(plugin.value)
            self.pm.register(module, name=plugin.value)

    @classmethod
    def core_only(cls) -> Self:
        """Build a manager with only the essential built-ins registered.

        Returns
        -------
        Self
            A manager with tier-1 plugins registered and registries built.
        """
        manager = cls()
        manager._register_builtins()
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
        manager._register_builtins()

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
                    name, partial(manager._load_path_module, name, init)
                )

        # Register tier-3 entry-point plugins, sorted so a registration clash
        # is reported against the same pair of plugins on every run.
        eps = sorted(
            importlib_metadata.entry_points(group=PLUGIN_ENTRY_POINT_GROUP),
            key=lambda ep: ep.name,
        )
        for ep in eps:
            manager._register_external(ep.name, ep.load)

        # Register tier-4 session plugins.
        for spec in extra_plugins:
            path = Path(spec)
            if path.exists():
                name = path.name if path.is_dir() else path.stem
                init = path / "__init__.py" if path.is_dir() else path
                load = partial(manager._load_path_module, name, init)
            else:
                name = spec
                load = partial(importlib.import_module, spec)
            manager._register_external(name, load)

        manager.build_registries()
        return manager
