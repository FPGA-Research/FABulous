"""Built-in management plugin: the ``plugins`` command surface and operations.

The operation functions are surface-agnostic so the cmd2 ``CommandSet`` and the
top-level Typer passthrough share one implementation.
"""

import argparse
import json
import shutil
import subprocess
import sys

import cmd2
from cmd2 import CommandSet, with_default_category

from fabulous.fabulous_settings import add_var_to_project_env, get_context
from fabulous.plugins import hookimpl
from fabulous.plugins.manager import FABulousPluginManager
from fabulous.plugins.types import PluginError


def _tier_of(manager: FABulousPluginManager, name: str) -> str:
    """Return a best-effort tier label for a registered plugin name."""
    if manager.isEssential(name):
        return "core"
    return "plugin"


def format_plugin_list(manager: FABulousPluginManager) -> str:
    """Return a human-readable listing of registered plugins.

    Parameters
    ----------
    manager : FABulousPluginManager
        The manager whose plugins are listed.

    Returns
    -------
    str
        The formatted listing.
    """
    disabled = set(get_context().plugins.disabled)
    rows = []
    for name, _ in sorted(manager.pm.list_name_plugin(), key=lambda kv: kv[0]):
        tier = _tier_of(manager, name)
        state = "disabled" if name in disabled else "enabled"
        rows.append(f"  {name:50s} {tier:8s} {state}")
    header = f"  {'name':50s} {'tier':8s} state"
    return "Plugins:\n" + header + "\n" + "\n".join(rows)


def format_plugin_info(manager: FABulousPluginManager, name: str) -> str:
    """Return detail for a single plugin, including contributed settings.

    Parameters
    ----------
    manager : FABulousPluginManager
        The manager to query.
    name : str
        The plugin name.

    Returns
    -------
    str
        The formatted detail.

    Raises
    ------
    PluginError
        If no plugin named ``name`` is registered.
    """
    if manager.pm.get_plugin(name) is None:
        raise PluginError(f"No plugin named '{name}'")
    lines = [f"Plugin: {name}", f"  tier: {_tier_of(manager, name)}"]
    spec = manager.get_setting_spec(name)
    if spec is not None:
        lines.append(f"  settings: {spec.name} (env prefix {spec.envPrefix})")
    return "\n".join(lines)


def set_plugin_enabled(
    manager: FABulousPluginManager, name: str, enabled: bool
) -> None:
    """Enable or disable a plugin by rewriting the project ``disabled`` list.

    Parameters
    ----------
    manager : FABulousPluginManager
        The manager (used to check essential built-ins).
    name : str
        The plugin name.
    enabled : bool
        ``True`` to enable, ``False`` to disable.

    Raises
    ------
    PluginError
        If an essential built-in is being disabled.
    """
    if not enabled and manager.isEssential(name):
        raise PluginError(f"'{name}' is an essential built-in and cannot be disabled.")
    disabled = list(get_context().plugins.disabled)
    if enabled:
        disabled = [d for d in disabled if d != name]
    elif name not in disabled:
        disabled.append(name)
    add_var_to_project_env("FAB_PLUGINS__DISABLED", json.dumps(disabled))


def install_plugin(spec: str) -> None:
    """Install a plugin package into the running environment via uv.

    Parameters
    ----------
    spec : str
        A uv/pip install specifier (package name, git URL, or local path).

    Raises
    ------
    PluginError
        If uv is not available.
    """
    uv = shutil.which("uv")
    if uv is None:
        raise PluginError("uv not found; uv is required to install plugins.")
    subprocess.run([uv, "pip", "install", "--python", sys.executable, spec], check=True)


def uninstall_plugin(name: str) -> None:
    """Uninstall a plugin package via uv.

    Parameters
    ----------
    name : str
        The package name to uninstall.

    Raises
    ------
    PluginError
        If uv is not available.
    """
    uv = shutil.which("uv")
    if uv is None:
        raise PluginError("uv not found; uv is required to uninstall plugins.")
    subprocess.run([uv, "pip", "uninstall", name], check=True)


def _build_parser() -> cmd2.Cmd2ArgumentParser:
    parser = cmd2.Cmd2ArgumentParser()
    sub = parser.add_subparsers(dest="action", required=True)
    sub.add_parser("list", help="List discovered plugins")
    info_p = sub.add_parser("info", help="Show plugin detail")
    info_p.add_argument("name")
    en_p = sub.add_parser("enable", help="Enable a plugin (restart to apply)")
    en_p.add_argument("name")
    dis_p = sub.add_parser("disable", help="Disable a plugin (restart to apply)")
    dis_p.add_argument("name")
    inst_p = sub.add_parser("install", help="Install a plugin package via uv")
    inst_p.add_argument("spec")
    uninst_p = sub.add_parser("uninstall", help="Uninstall a plugin package via uv")
    uninst_p.add_argument("name")
    return parser


@with_default_category("Plugins")
class PluginCommands(CommandSet):
    """The shell ``plugins ...`` command surface."""

    @cmd2.with_argparser(_build_parser())
    def do_plugins(self, args: argparse.Namespace) -> None:
        """Manage FABulous plugins."""
        manager = self._cmd.pluginManager
        action = args.action
        if action == "list":
            self._cmd.poutput(format_plugin_list(manager))
        elif action == "info":
            self._cmd.poutput(format_plugin_info(manager, args.name))
        elif action == "enable":
            set_plugin_enabled(manager, args.name, enabled=True)
            self._cmd.poutput(f"Enabled '{args.name}'. Restart to apply.")
        elif action == "disable":
            set_plugin_enabled(manager, args.name, enabled=False)
            self._cmd.poutput(f"Disabled '{args.name}'. Restart to apply.")
        elif action == "install":
            install_plugin(args.spec)
            self._cmd.poutput("Installed. Restart FABulous to load the plugin.")
        elif action == "uninstall":
            uninstall_plugin(args.name)
            self._cmd.poutput("Uninstalled. Restart FABulous to apply.")


@hookimpl
def fabulous_register_commands() -> CommandSet:
    """Contribute the management command set to the shell.

    The command set reaches the shell and manager via ``self._cmd``, so the
    ``cli`` hook argument is not needed here (pluggy passes only declared args).

    Returns
    -------
    CommandSet
        The management command set.
    """
    return PluginCommands()
