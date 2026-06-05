"""The FABulous plugin manager: discovery authority and provider registries."""

import importlib
import importlib.metadata as importlib_metadata
import importlib.util
from pathlib import Path
from typing import TYPE_CHECKING

import pluggy
from loguru import logger

from fabulous.fabric_definition.define import HDLType
from fabulous.fabulous_settings import get_context
from fabulous.plugins import hookspecs
from fabulous.plugins.types import (
    CodeGeneratorProvider,
    ParserProvider,
    PluginError,
    PluginSettingsSpec,
)

if TYPE_CHECKING:
    from collections.abc import Callable

    from fabulous.fabric_definition.fabric import Fabric
    from fabulous.fabric_generator.code_generator.code_generator import CodeGenerator

DEFAULT_PLUGINS = (
    "fabulous.plugins.management",
    "fabulous.fabric_generator.code_generator.plugin",
    "fabulous.fabric_generator.parser.plugin",
)

# v1: every built-in is essential (cannot be disabled). The split exists so
# future migrated features can ship as disableable default plugins.
ESSENTIAL_PLUGINS = frozenset(DEFAULT_PLUGINS)


class FABulousPluginManager:
    """Owns plugin discovery, lifecycle, and the provider registries."""

    def __init__(self) -> None:
        self.pm = pluggy.PluginManager("fabulous")
        self.pm.add_hookspecs(hookspecs)
        self._codegens: dict[HDLType, CodeGeneratorProvider] = {}
        self._parsers: dict[str, ParserProvider] = {}
        self._settings: dict[str, object] = {}
        self._settingSpecs: dict[str, PluginSettingsSpec] = {}

    def isEssential(self, name: str) -> bool:
        """Return whether ``name`` is an essential built-in plugin.

        Parameters
        ----------
        name : str
            The plugin name to check.

        Returns
        -------
        bool
            ``True`` if the plugin is an essential built-in.
        """
        return name in ESSENTIAL_PLUGINS

    def build_registries(self) -> None:
        """Fold the aggregating hooks into keyed registries.

        Raises
        ------
        PluginError
            If two providers claim the same HDL type or file suffix, or if two
            settings specs share a name.
        """
        self._codegens.clear()
        for providers in self.pm.hook.fabulous_register_code_generators():
            for provider in providers:
                existing = self._codegens.get(provider.hdlType)
                if existing is not None:
                    raise PluginError(
                        f"HDLType {provider.hdlType.name} registered by both "
                        f"'{existing.name}' and '{provider.name}'"
                    )
                self._codegens[provider.hdlType] = provider

        self._parsers.clear()
        for providers in self.pm.hook.fabulous_register_parsers():
            for provider in providers:
                existing = self._parsers.get(provider.suffix)
                if existing is not None:
                    raise PluginError(
                        f"Parser suffix '{provider.suffix}' registered by both "
                        f"'{existing.name}' and '{provider.name}'"
                    )
                self._parsers[provider.suffix] = provider

        self._settings.clear()
        self._settingSpecs.clear()
        for spec in self.pm.hook.fabulous_register_settings():
            if spec is None:
                continue
            if spec.name in self._settingSpecs:
                raise PluginError(
                    f"Settings group '{spec.name}' registered more than once"
                )
            self._settingSpecs[spec.name] = spec
            self._settings[spec.name] = spec.model()

    def get_code_generator(self, hdlType: HDLType) -> "CodeGenerator":
        """Return a fresh code generator for ``hdlType``.

        Parameters
        ----------
        hdlType : HDLType
            The HDL language to resolve a generator for.

        Returns
        -------
        CodeGenerator
            A fresh generator instance from the registered provider.

        Raises
        ------
        PluginError
            If no provider is registered for ``hdlType``.
        """
        key = HDLType(hdlType)
        provider = self._codegens.get(key)
        if provider is None:
            available = ", ".join(sorted(h.value for h in self._codegens))
            raise PluginError(
                f"No code generator registered for '{key.value}'. "
                f"Available: {available or '(none)'}"
            )
        return provider.factory()

    def get_parser(self, suffix: str) -> "Callable[[Path], Fabric]":
        """Return the parse callable for a file ``suffix`` (e.g. ``.csv``).

        Parameters
        ----------
        suffix : str
            The file suffix including the dot.

        Returns
        -------
        Callable[[Path], Fabric]
            The parse callable from the registered provider.

        Raises
        ------
        PluginError
            If no parser is registered for ``suffix``.
        """
        provider = self._parsers.get(suffix)
        if provider is None:
            available = ", ".join(sorted(self._parsers))
            raise PluginError(
                f"No parser registered for suffix '{suffix}'. "
                f"Available: {available or '(none)'}"
            )
        return provider.parse

    def get_settings(self, name: str) -> object:
        """Return a plugin's instantiated settings model by group name.

        Parameters
        ----------
        name : str
            The settings group name.

        Returns
        -------
        object
            The instantiated settings model.

        Raises
        ------
        PluginError
            If no settings group named ``name`` was registered.
        """
        if name not in self._settings:
            raise PluginError(f"No settings group named '{name}'")
        return self._settings[name]

    def get_setting_spec(self, name: str) -> "PluginSettingsSpec | None":
        """Return the settings spec for a plugin group, or ``None``.

        Parameters
        ----------
        name : str
            The settings group name.

        Returns
        -------
        PluginSettingsSpec | None
            The registered spec, or ``None`` if the group is unknown.
        """
        return self._settingSpecs.get(name)

    def _handle_broken(self, name: str, exc: Exception, skip_broken: bool) -> None:
        """Apply the broken-plugin policy to a failed optional plugin.

        Parameters
        ----------
        name : str
            The plugin name that failed.
        exc : Exception
            The exception raised during load or registration.
        skip_broken : bool
            Whether to warn and continue instead of aborting.

        Raises
        ------
        PluginError
            When ``skip_broken`` is false; the message names the plugin and the
            remedy command.
        """
        if skip_broken:
            logger.warning(f"Skipping broken plugin '{name}': {exc}")
            return
        raise PluginError(
            f"Plugin '{name}' failed to load: {exc}\n"
            f"Disable it with: FABulous plugins disable {name}"
        ) from exc

    def register_builtins(self) -> None:
        """Register the essential built-in plugins (tier 1). Always fail loud."""
        for dotted in DEFAULT_PLUGINS:
            module = importlib.import_module(dotted)
            self.pm.register(module, name=dotted)

    def discover_dir(self, base: Path, skip_broken: bool) -> None:
        """Register tier-2 sub-plugins found as packages under ``base``.

        Parameters
        ----------
        base : Path
            Directory whose immediate package subdirectories are scanned.
        skip_broken : bool
            Whether to warn and continue when a plugin fails to load.
        """
        if not base.is_dir():
            return
        for child in sorted(base.iterdir(), key=lambda p: p.name):
            init = child / "__init__.py"
            if not child.is_dir() or not init.exists():
                continue
            name = child.name
            if self.pm.is_blocked(name):
                continue
            try:
                spec = importlib.util.spec_from_file_location(name, init)
                module = importlib.util.module_from_spec(spec)
                spec.loader.exec_module(module)
                self.pm.register(module, name=name)
            except Exception as exc:  # noqa: BLE001 - policy decides re-raise
                self._handle_broken(name, exc, skip_broken)

    def discover_entrypoints(self, skip_broken: bool) -> None:
        """Register tier-3 third-party plugins from the entry-point group.

        Parameters
        ----------
        skip_broken : bool
            Whether to warn and continue when a plugin fails to load.
        """
        eps = sorted(
            importlib_metadata.entry_points(group="fabulous.plugins"),
            key=lambda ep: ep.name,
        )
        for ep in eps:
            if self.pm.is_blocked(ep.name):
                continue
            try:
                module = ep.load()
                self.pm.register(module, name=ep.name)
            except Exception as exc:  # noqa: BLE001 - policy decides re-raise
                self._handle_broken(ep.name, exc, skip_broken)

    def register_session(self, spec: str, skip_broken: bool) -> None:
        """Register a tier-4 session plugin (a dotted path or a local dir/file).

        Parameters
        ----------
        spec : str
            A dotted module path, or a path to a package directory or module file.
        skip_broken : bool
            Whether to warn and continue when the plugin fails to load.
        """
        try:
            path = Path(spec)
            if path.exists():
                init = path / "__init__.py" if path.is_dir() else path
                name = path.name if path.is_dir() else path.stem
                module_spec = importlib.util.spec_from_file_location(name, init)
                module = importlib.util.module_from_spec(module_spec)
                module_spec.loader.exec_module(module)
                self.pm.register(module, name=name)
            else:
                module = importlib.import_module(spec)
                self.pm.register(module, name=spec)
        except Exception as exc:  # noqa: BLE001 - policy decides re-raise
            self._handle_broken(spec, exc, skip_broken)

    @classmethod
    def core_only(cls) -> "FABulousPluginManager":
        """Build a manager with only the essential built-ins registered.

        Returns
        -------
        FABulousPluginManager
            A manager with tier-1 plugins registered and registries built.
        """
        manager = cls()
        manager.register_builtins()
        manager.build_registries()
        return manager

    @classmethod
    def create(
        cls, extra_plugins: tuple[str, ...] = (), skip_broken: bool | None = None
    ) -> "FABulousPluginManager":
        """Build a fully discovered manager across all tiers.

        Parameters
        ----------
        extra_plugins : tuple[str, ...]
            Tier-4 session plugins (``-m/--plugin`` values).
        skip_broken : bool | None
            Override for ``plugins.skip_broken``; ``None`` uses the setting.

        Returns
        -------
        FABulousPluginManager
            The populated manager, after ``fabulous_startup`` has fired.
        """
        settings = get_context().plugins
        if skip_broken is None:
            skip_broken = settings.skip_broken

        manager = cls()
        manager.register_builtins()

        for name in sorted(set(settings.disabled)):
            manager.pm.set_blocked(name)

        plugin_dir = settings.dir
        if not plugin_dir.is_absolute():
            plugin_dir = get_context().proj_dir / plugin_dir
        manager.discover_dir(plugin_dir, skip_broken)
        manager.discover_entrypoints(skip_broken)
        for spec in extra_plugins:
            manager.register_session(spec, skip_broken)

        manager.build_registries()
        manager.pm.hook.fabulous_startup(manager=manager)
        return manager
