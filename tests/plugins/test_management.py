"""Management operations: list, enable/disable, install."""

import json

import pytest
from pytest_mock import MockerFixture

from fabulous.plugins import management
from fabulous.plugins.manager import DEFAULT_PLUGINS, FABulousPluginManager
from fabulous.plugins.types import PluginError


def test_format_plugin_list_includes_builtins(mocker: MockerFixture) -> None:
    mocker.patch.object(management, "get_context").return_value.plugins.disabled = []
    manager = FABulousPluginManager.core_only()
    text = management.format_plugin_list(manager)
    for dotted in DEFAULT_PLUGINS:
        assert dotted in text


def test_disable_essential_refuses() -> None:
    manager = FABulousPluginManager.core_only()
    with pytest.raises(PluginError):
        management.set_plugin_enabled(
            manager, "fabulous.plugins.management", enabled=False
        )


def test_disable_optional_writes_config(mocker: MockerFixture) -> None:
    manager = FABulousPluginManager.core_only()
    mocker.patch.object(management, "get_context").return_value.plugins.disabled = []
    written = mocker.patch.object(management, "add_var_to_project_env")
    management.set_plugin_enabled(manager, "some_optional", enabled=False)
    written.assert_called_once()
    key, value = written.call_args.args
    assert key == "FAB_PLUGINS__DISABLED"
    assert json.loads(value) == ["some_optional"]


def test_install_invokes_uv(mocker: MockerFixture) -> None:
    mocker.patch.object(management.shutil, "which", return_value="/usr/bin/uv")
    run = mocker.patch.object(management.subprocess, "run")
    management.install_plugin("some-package")
    args = run.call_args.args[0]
    assert args[0] == "/usr/bin/uv"
    assert args[1:4] == ["pip", "install", "--python"]
    assert args[-1] == "some-package"


def test_install_without_uv_errors(mocker: MockerFixture) -> None:
    mocker.patch.object(management.shutil, "which", return_value=None)
    with pytest.raises(PluginError):
        management.install_plugin("some-package")
