"""Discovery tiers: core, dir-scan, entry points, session, broken."""

import types
from pathlib import Path

import pytest
from pytest_mock import MockerFixture

from fabulous.fabric_definition.define import HDLType
from fabulous.plugins import PLUGIN_API_VERSION
from fabulous.plugins import manager as manager_module
from fabulous.plugins.manager import BuiltinPlugin, PluginManager
from fabulous.plugins.types import PluginError

PLUGIN_SRC = """
from fabulous.plugins import PLUGIN_API_VERSION, hookimpl
from fabulous.plugins.types import ParserProvider

FABULOUS_PLUGIN_API = PLUGIN_API_VERSION


@hookimpl
def fabulous_register_parsers():
    return [ParserProvider("{suffix}", lambda path: path, "{name}")]
"""


def _write_dir_plugin(base: Path, name: str, suffix: str) -> None:
    pkg = base / name
    pkg.mkdir(parents=True)
    (pkg / "__init__.py").write_text(PLUGIN_SRC.format(suffix=suffix, name=name))


def _patch_context(
    mocker: MockerFixture, plugin_dir: Path, *, skip_broken: bool = False
) -> None:
    """Point `create()` at `plugin_dir` for tier-2 dir-scan discovery."""
    ctx = mocker.patch.object(manager_module, "get_context").return_value
    ctx.plugin_dir = plugin_dir
    ctx.skip_broken_plugins = skip_broken
    ctx.proj_dir = plugin_dir


def test_core_only_registers_default_plugins() -> None:
    manager = PluginManager.core_only()
    for plugin in BuiltinPlugin:
        assert manager.pm.get_plugin(plugin.value) is not None
    assert manager.make_writer(HDLType.VERILOG).file_extension == ".v"
    assert manager.make_parser(Path("fabric.csv")) is not None


def test_dir_scan_registers_subpackages(tmp_path: Path, mocker: MockerFixture) -> None:
    _write_dir_plugin(tmp_path, "alpha", ".a")
    _patch_context(mocker, tmp_path)
    manager = PluginManager.create()
    assert manager.make_parser(Path("fabric.a")) is not None


def test_dir_scan_is_sorted(tmp_path: Path, mocker: MockerFixture) -> None:
    _write_dir_plugin(tmp_path, "bbb", ".b")
    _write_dir_plugin(tmp_path, "aaa", ".a")
    _patch_context(mocker, tmp_path)
    manager = PluginManager.create()
    names = [n for n, _ in manager.pm.list_name_plugin() if n in {"aaa", "bbb"}]
    assert names == sorted(names)


def test_entrypoint_discovery(tmp_path: Path, mocker: MockerFixture) -> None:
    ep_module = types.ModuleType("ep_plugin")
    from fabulous.plugins import hookimpl
    from fabulous.plugins.types import ParserProvider

    @hookimpl
    def fabulous_register_parsers() -> list[ParserProvider]:
        return [ParserProvider(".ep", lambda path: path, "ep")]

    ep_module.fabulous_register_parsers = fabulous_register_parsers
    ep_module.FABULOUS_PLUGIN_API = PLUGIN_API_VERSION
    fake_ep = types.SimpleNamespace(name="ep", load=lambda: ep_module)
    mocker.patch.object(
        manager_module.importlib_metadata,
        "entry_points",
        return_value=[fake_ep],
    )
    _patch_context(mocker, tmp_path / "plugins")  # absent dir -> tier-2 no-op
    manager = PluginManager.create()
    assert manager.make_parser(Path("fabric.ep")) is not None


def test_session_plugin_dir(tmp_path: Path, mocker: MockerFixture) -> None:
    _write_dir_plugin(tmp_path, "sess", ".s")
    _patch_context(mocker, tmp_path / "plugins")
    manager = PluginManager.create(extra_plugins=(str(tmp_path / "sess"),))
    assert manager.make_parser(Path("fabric.s")) is not None


def test_broken_plugin_strict_aborts(tmp_path: Path, mocker: MockerFixture) -> None:
    pkg = tmp_path / "broke"
    pkg.mkdir()
    (pkg / "__init__.py").write_text("raise ImportError('boom')")
    _patch_context(mocker, tmp_path, skip_broken=False)
    with pytest.raises(PluginError) as exc:
        PluginManager.create()
    assert "broke" in str(exc.value)


def test_broken_plugin_skip_warns(tmp_path: Path, mocker: MockerFixture) -> None:
    pkg = tmp_path / "broke"
    pkg.mkdir()
    (pkg / "__init__.py").write_text("raise ImportError('boom')")
    _patch_context(mocker, tmp_path, skip_broken=True)
    manager = PluginManager.create()
    assert manager.pm.get_plugin("broke") is None


def test_incompatible_api_aborts(tmp_path: Path, mocker: MockerFixture) -> None:
    pkg = tmp_path / "oldplug"
    pkg.mkdir()
    (pkg / "__init__.py").write_text("FABULOUS_PLUGIN_API = -1\n")
    _patch_context(mocker, tmp_path, skip_broken=False)
    with pytest.raises(PluginError) as exc:
        PluginManager.create()
    assert "oldplug" in str(exc.value)


def test_missing_api_declaration_aborts(tmp_path: Path, mocker: MockerFixture) -> None:
    pkg = tmp_path / "noversion"
    pkg.mkdir()
    (pkg / "__init__.py").write_text("x = 1\n")
    _patch_context(mocker, tmp_path, skip_broken=False)
    with pytest.raises(PluginError):
        PluginManager.create()


def test_incompatible_api_skipped_when_lenient(
    tmp_path: Path, mocker: MockerFixture
) -> None:
    pkg = tmp_path / "oldplug"
    pkg.mkdir()
    (pkg / "__init__.py").write_text("FABULOUS_PLUGIN_API = -1\n")
    _patch_context(mocker, tmp_path, skip_broken=True)
    manager = PluginManager.create()
    assert manager.pm.get_plugin("oldplug") is None
