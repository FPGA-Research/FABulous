"""Management operations: list, info, and uv-backed install."""

import sys
import types
from importlib.metadata import PackageNotFoundError, version

from pytest_mock import MockerFixture

from fabulous.plugins import hookimpl
from fabulous.plugins import manager as manager_module
from fabulous.plugins.manager import BuiltinPlugin, PluginManager


def test_format_plugin_list_includes_builtins(mocker: MockerFixture) -> None:
    mocker.patch.object(manager_module, "get_context")
    manager = PluginManager.core_only()
    text = manager.get_installed_plugins_str()
    for plugin in BuiltinPlugin:
        assert plugin.value in text


def test_plugin_version_essential_uses_fabulous_version(
    mocker: MockerFixture,
) -> None:
    mocker.patch.object(manager_module, "get_context")
    manager = PluginManager.core_only()
    info = manager.get_plugin_info_str(BuiltinPlugin.CODE_GENERATORS.value)
    assert f"version: {version('FABulous-FPGA')}" in info


def test_plugin_version_from_module_dunder(mocker: MockerFixture) -> None:
    mocker.patch.object(manager_module, "get_context")
    manager = PluginManager.core_only()
    module = types.ModuleType("versioned_plugin")
    module.__version__ = "1.2.3"
    manager.pm.register(module, name="versioned_plugin")
    assert "version: 1.2.3" in manager.get_plugin_info_str("versioned_plugin")


def test_plugin_version_falls_back_to_distribution_name(
    mocker: MockerFixture,
) -> None:
    mocker.patch.object(manager_module, "get_context")
    manager = PluginManager.core_only()
    module = types.ModuleType("some_pkg")
    manager.pm.register(module, name="some_pkg")

    def fake_version(name: str) -> str:
        if name == "some_pkg":
            return "9.9.9"
        raise PackageNotFoundError(name)

    mocker.patch.object(manager_module.importlib_metadata, "version", fake_version)
    assert "version: 9.9.9" in manager.get_plugin_info_str("some_pkg")


def test_plugin_version_falls_back_to_top_level_distribution(
    mocker: MockerFixture,
) -> None:
    mocker.patch.object(manager_module, "get_context")
    manager = PluginManager.core_only()
    module = types.ModuleType("registration_name")
    module.__name__ = "some_module.submodule"
    manager.pm.register(module, name="registration_name")

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
    assert "version: 4.5.6" in manager.get_plugin_info_str("registration_name")


def test_plugin_version_unknown_when_unresolvable(mocker: MockerFixture) -> None:
    mocker.patch.object(manager_module, "get_context")
    manager = PluginManager.core_only()
    module = types.ModuleType("unresolvable_plugin")
    manager.pm.register(module, name="unresolvable_plugin")
    info = manager.get_plugin_info_str("unresolvable_plugin")
    assert "version: unknown" in info


def test_install_invokes_uv(mocker: MockerFixture) -> None:
    mocker.patch.object(manager_module, "find_uv_bin", return_value="/usr/bin/uv")
    run = mocker.patch.object(manager_module.subprocess, "run")
    PluginManager().install("some-package")
    args = run.call_args.args[0]
    assert args[0] == "/usr/bin/uv"
    assert args[1:4] == ["pip", "install", "--python"]
    assert args[-1] == "some-package"


def test_uninstall_invokes_uv(mocker: MockerFixture) -> None:
    mocker.patch.object(manager_module, "find_uv_bin", return_value="/usr/bin/uv")
    run = mocker.patch.object(manager_module.subprocess, "run")
    PluginManager().uninstall("some-package")
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
        PluginManager,
        "installed_plugins",
        new_callable=mocker.PropertyMock,
        side_effect=[set(), {"newplug"}],
    )
    assert PluginManager().install("some-pkg") == (
        True,
        "Installed. Added plugin(s): newplug.",
    )


def test_notify_fabric_loaded_invokes_hook() -> None:
    manager = PluginManager.core_only()
    received = []
    module = types.ModuleType("after_load_plugin")

    @hookimpl
    def fabulous_after_fabric_loaded(api: object) -> None:
        received.append(api)

    module.fabulous_after_fabric_loaded = fabulous_after_fabric_loaded
    manager.pm.register(module, name="after_load")

    sentinel = object()
    manager.notify_fabric_loaded(sentinel)

    assert received == [sentinel]
