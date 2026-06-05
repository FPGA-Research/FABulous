"""Discovery tiers: core, dir-scan, entry points, session, disable, broken."""

import types
from pathlib import Path

import pytest

from fabulous.fabric_definition.define import HDLType
from fabulous.plugins import manager as manager_module
from fabulous.plugins.manager import DEFAULT_PLUGINS, FABulousPluginManager
from fabulous.plugins.types import PluginError

PLUGIN_SRC = """
from fabulous.plugins import hookimpl
from fabulous.plugins.types import ParserProvider


@hookimpl
def fabulous_register_parsers():
    return [ParserProvider("{suffix}", lambda path: path, "{name}")]
"""


def _write_dir_plugin(base: Path, name: str, suffix: str) -> None:
    pkg = base / name
    pkg.mkdir(parents=True)
    (pkg / "__init__.py").write_text(PLUGIN_SRC.format(suffix=suffix, name=name))


def test_core_only_registers_default_plugins() -> None:
    manager = FABulousPluginManager.core_only()
    for dotted in DEFAULT_PLUGINS:
        assert manager.pm.get_plugin(dotted) is not None
    assert manager.get_code_generator(HDLType.VERILOG).fileExtension == ".v"
    assert manager.get_parser(".csv") is not None


def test_dir_scan_registers_subpackages(tmp_path: Path) -> None:
    _write_dir_plugin(tmp_path, "alpha", ".a")
    manager = FABulousPluginManager.core_only()
    manager.discover_dir(tmp_path, skip_broken=False)
    manager.build_registries()
    assert manager.get_parser(".a") is not None


def test_dir_scan_is_sorted(tmp_path: Path) -> None:
    _write_dir_plugin(tmp_path, "bbb", ".b")
    _write_dir_plugin(tmp_path, "aaa", ".a")
    manager = FABulousPluginManager.core_only()
    manager.discover_dir(tmp_path, skip_broken=False)
    names = [n for n, _ in manager.pm.list_name_plugin() if n in {"aaa", "bbb"}]
    assert names == sorted(names)


def test_disabled_plugin_is_blocked(tmp_path: Path) -> None:
    _write_dir_plugin(tmp_path, "alpha", ".a")
    manager = FABulousPluginManager.core_only()
    manager.pm.set_blocked("alpha")
    manager.discover_dir(tmp_path, skip_broken=False)
    assert manager.pm.get_plugin("alpha") is None


def test_entrypoint_discovery(monkeypatch: pytest.MonkeyPatch) -> None:
    ep_module = types.ModuleType("ep_plugin")
    from fabulous.plugins import hookimpl
    from fabulous.plugins.types import ParserProvider

    @hookimpl
    def fabulous_register_parsers() -> list[ParserProvider]:
        return [ParserProvider(".ep", lambda path: path, "ep")]

    ep_module.fabulous_register_parsers = fabulous_register_parsers
    fake_ep = types.SimpleNamespace(name="ep", load=lambda: ep_module)
    monkeypatch.setattr(
        manager_module.importlib_metadata,
        "entry_points",
        lambda group: [fake_ep],  # noqa: ARG005 - signature must match entry_points
    )
    manager = FABulousPluginManager.core_only()
    manager.discover_entrypoints(skip_broken=False)
    manager.build_registries()
    assert manager.get_parser(".ep") is not None


def test_session_plugin_dir(tmp_path: Path) -> None:
    _write_dir_plugin(tmp_path, "sess", ".s")
    manager = FABulousPluginManager.core_only()
    manager.register_session(str(tmp_path / "sess"), skip_broken=False)
    manager.build_registries()
    assert manager.get_parser(".s") is not None


def test_broken_plugin_strict_aborts(tmp_path: Path) -> None:
    pkg = tmp_path / "broke"
    pkg.mkdir()
    (pkg / "__init__.py").write_text("raise ImportError('boom')")
    manager = FABulousPluginManager.core_only()
    with pytest.raises(PluginError) as exc:
        manager.discover_dir(tmp_path, skip_broken=False)
    assert "broke" in str(exc.value)


def test_broken_plugin_skip_warns(tmp_path: Path) -> None:
    pkg = tmp_path / "broke"
    pkg.mkdir()
    (pkg / "__init__.py").write_text("raise ImportError('boom')")
    manager = FABulousPluginManager.core_only()
    manager.discover_dir(tmp_path, skip_broken=True)
    assert manager.pm.get_plugin("broke") is None
