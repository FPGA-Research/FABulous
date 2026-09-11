"""Management operations: list, info and uv-backed install."""

import sys
import types
from importlib.metadata import PackageNotFoundError, version

import pytest
from pytest_mock import MockerFixture

from fabulous.plugins import manager as manager_module
from fabulous.plugins.manager import BuiltinPlugin, PluginManager


@pytest.fixture
def core_manager(mocker: MockerFixture) -> PluginManager:
    """A built-ins-only manager whose settings store is a mock, not a project."""
    mocker.patch.object(manager_module, "get_context")
    return PluginManager.core_only()


def test_format_plugin_list_includes_builtins(core_manager: PluginManager) -> None:
    text = core_manager.get_installed_plugins_str()
    for plugin in BuiltinPlugin:
        assert plugin.value in text


def test_plugin_version_essential_uses_fabulous_version(
    core_manager: PluginManager,
) -> None:
    info = core_manager.get_plugin_info_str(BuiltinPlugin.CODE_GENERATORS.value)
    assert f"version: {version('FABulous-FPGA')}" in info


def test_plugin_version_from_module_dunder(core_manager: PluginManager) -> None:
    module = types.ModuleType("versioned_plugin")
    module.__version__ = "1.2.3"
    core_manager.pm.register(module, name="versioned_plugin")
    assert "version: 1.2.3" in core_manager.get_plugin_info_str("versioned_plugin")


def test_plugin_version_falls_back_to_distribution_name(
    core_manager: PluginManager, mocker: MockerFixture
) -> None:
    module = types.ModuleType("some_pkg")
    core_manager.pm.register(module, name="some_pkg")

    def fake_version(name: str) -> str:
        if name == "some_pkg":
            return "9.9.9"
        raise PackageNotFoundError(name)

    mocker.patch.object(manager_module.importlib_metadata, "version", fake_version)
    assert "version: 9.9.9" in core_manager.get_plugin_info_str("some_pkg")


def test_plugin_version_falls_back_to_top_level_distribution(
    core_manager: PluginManager, mocker: MockerFixture
) -> None:
    module = types.ModuleType("some_module.submodule")
    core_manager.pm.register(module, name="some_module.submodule")

    def fake_version(name: str) -> str:
        if name == "real-dist-name":
            return "4.5.6"
        raise PackageNotFoundError(name)

    mocker.patch.object(manager_module.importlib_metadata, "version", fake_version)
    mocker.patch.object(
        manager_module.importlib_metadata,
        "packages_distributions",
        return_value={"some_module": ["real-dist-name"]},
    )
    assert "version: 4.5.6" in core_manager.get_plugin_info_str("some_module.submodule")


def test_plugin_version_unknown_when_unresolvable(
    core_manager: PluginManager,
) -> None:
    module = types.ModuleType("unresolvable_plugin")
    core_manager.pm.register(module, name="unresolvable_plugin")
    info = core_manager.get_plugin_info_str("unresolvable_plugin")
    assert "version: unknown" in info


def test_install_invokes_uv(mocker: MockerFixture) -> None:
    mocker.patch.object(manager_module, "find_uv_bin", return_value="/usr/bin/uv")
    run = mocker.patch.object(manager_module.subprocess, "run")
    PluginManager.install("some-package")
    args = run.call_args.args[0]
    assert args[0] == "/usr/bin/uv"
    assert args[1:4] == ["pip", "install", "--python"]
    assert args[-1] == "some-package"


def test_uninstall_invokes_uv(mocker: MockerFixture) -> None:
    mocker.patch.object(manager_module, "find_uv_bin", return_value="/usr/bin/uv")
    run = mocker.patch.object(manager_module.subprocess, "run")
    PluginManager.uninstall("some-package")
    args = run.call_args.args[0]
    assert args[0] == "/usr/bin/uv"
    # uninstall must pin the same interpreter as install, else it targets the
    # wrong environment (e.g. VIRTUAL_ENV) and removes nothing.
    assert args[1:4] == ["pip", "uninstall", "--python"]
    assert args[4] == sys.executable
    assert args[-1] == "some-package"


def test_install_reports_registered_plugin(mocker: MockerFixture) -> None:
    mocker.patch.object(manager_module, "find_uv_bin", return_value="/usr/bin/uv")
    mocker.patch.object(manager_module.subprocess, "run")
    # uv adds a new entry point between the before/after snapshots.
    mocker.patch.object(
        PluginManager, "installed_plugins", side_effect=[set(), {"newplug"}]
    )
    assert PluginManager.install("some-pkg") == (
        True,
        "Installed. Added plugin(s): newplug.",
    )


def test_uninstall_reports_when_nothing_was_removed(mocker: MockerFixture) -> None:
    """A package that owned no entry point is reported as such, not as removed."""
    mocker.patch.object(manager_module, "find_uv_bin", return_value="/usr/bin/uv")
    mocker.patch.object(manager_module.subprocess, "run")
    mocker.patch.object(PluginManager, "installed_plugins", side_effect=[set(), set()])

    removed, message = PluginManager.uninstall("some-pkg")

    assert removed is False
    assert "no plugin entry points disappeared" in message
