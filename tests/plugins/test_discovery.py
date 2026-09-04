"""Discovery tiers: core, dir-scan, entry points, session, broken."""

import sys
import types
from pathlib import Path

import pytest
from pytest_mock import MockerFixture

from fabulous.custom_exception import PluginError
from fabulous.fabric_definition.define import HDLType
from fabulous.plugins import PLUGIN_API_VERSION
from fabulous.plugins import manager as manager_module
from fabulous.plugins.manager import BuiltinPlugin, PluginManager

PLUGIN_SRC = """
from fabulous.plugins import PLUGIN_API_VERSION, hookimpl
from fabulous.plugins.types import ParserProvider

FABULOUS_PLUGIN_API = PLUGIN_API_VERSION


@hookimpl
def fabulous_register_parsers():
    return [ParserProvider(suffix="{suffix}", parse=lambda path: path, name="{name}")]
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
        return [ParserProvider(suffix=".ep", parse=lambda path: path, name="ep")]

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


def test_package_plugin_resolves_relative_import(
    tmp_path: Path, mocker: MockerFixture
) -> None:
    """A multi-file plugin package may import its own submodules.

    Executing the module without a `sys.modules` entry leaves the relative
    import with no parent package to resolve against.
    """
    pkg = tmp_path / "multi"
    pkg.mkdir()
    (pkg / "provider.py").write_text(PLUGIN_SRC.format(suffix=".m", name="multi"))
    (pkg / "__init__.py").write_text(
        "from fabulous.plugins import PLUGIN_API_VERSION\n"
        "from .provider import fabulous_register_parsers\n"
        "FABULOUS_PLUGIN_API = PLUGIN_API_VERSION\n"
    )
    _patch_context(mocker, tmp_path)

    manager = PluginManager.create()

    assert manager.make_parser(Path("fabric.m")) is not None


def test_failed_load_leaves_no_sys_modules_entry(
    tmp_path: Path, mocker: MockerFixture
) -> None:
    """A half-executed plugin must not shadow a real module of the same name."""
    pkg = tmp_path / "halfdead"
    pkg.mkdir()
    (pkg / "__init__.py").write_text("raise ImportError('boom')")
    _patch_context(mocker, tmp_path, skip_broken=True)

    PluginManager.create()

    assert "halfdead" not in sys.modules


def test_broken_hook_keeps_builtin_providers(
    tmp_path: Path, mocker: MockerFixture
) -> None:
    """Skipping a broken plugin must not take the built-in generators with it.

    The hooks aggregate across plugins, so a single raising implementation
    would otherwise empty the whole registry it contributes to.
    """
    pkg = tmp_path / "raiser"
    pkg.mkdir()
    (pkg / "__init__.py").write_text(
        "from fabulous.plugins import PLUGIN_API_VERSION, hookimpl\n"
        "FABULOUS_PLUGIN_API = PLUGIN_API_VERSION\n"
        "@hookimpl\n"
        "def fabulous_register_code_generators():\n"
        "    raise RuntimeError('boom')\n"
    )
    _patch_context(mocker, tmp_path, skip_broken=True)

    manager = PluginManager.create()

    assert manager.make_writer(HDLType.VERILOG).file_extension == ".v"
    assert manager.pm.get_plugin("raiser") is None


def test_broken_hook_strict_names_the_plugin(
    tmp_path: Path, mocker: MockerFixture
) -> None:
    """Without `skip_broken`, a raising hook aborts and says which plugin raised."""
    pkg = tmp_path / "raiser"
    pkg.mkdir()
    (pkg / "__init__.py").write_text(
        "from fabulous.plugins import PLUGIN_API_VERSION, hookimpl\n"
        "FABULOUS_PLUGIN_API = PLUGIN_API_VERSION\n"
        "@hookimpl\n"
        "def fabulous_register_code_generators():\n"
        "    raise RuntimeError('boom')\n"
    )
    _patch_context(mocker, tmp_path, skip_broken=False)

    with pytest.raises(PluginError) as exc:
        PluginManager.create()

    assert "raiser" in str(exc.value)


def test_skip_broken_defaults_to_the_setting(
    tmp_path: Path, mocker: MockerFixture
) -> None:
    """`create(skip_broken=None)` reads `skip_broken_plugins` off the context."""
    pkg = tmp_path / "broke"
    pkg.mkdir()
    (pkg / "__init__.py").write_text("raise ImportError('boom')")
    _patch_context(mocker, tmp_path, skip_broken=True)

    manager = PluginManager.create(skip_broken=None)

    assert manager.pm.get_plugin("broke") is None


TYPO_HOOK_SRC = """
from fabulous.plugins import PLUGIN_API_VERSION, hookimpl

FABULOUS_PLUGIN_API = PLUGIN_API_VERSION


@hookimpl
def fabulous_register_code_generator():
    return []
"""


def test_unknown_hook_name_aborts(tmp_path: Path, mocker: MockerFixture) -> None:
    """A misspelled hook name is a load failure, not a silently inert plugin."""
    pkg = tmp_path / "typoplug"
    pkg.mkdir()
    (pkg / "__init__.py").write_text(TYPO_HOOK_SRC)
    _patch_context(mocker, tmp_path, skip_broken=False)

    with pytest.raises(PluginError) as exc:
        PluginManager.create()

    assert "typoplug" in str(exc.value)


def test_unknown_hook_name_skipped_when_lenient(
    tmp_path: Path, mocker: MockerFixture
) -> None:
    """`skip_broken` covers a misspelled hook like any other load failure."""
    pkg = tmp_path / "typoplug"
    pkg.mkdir()
    (pkg / "__init__.py").write_text(TYPO_HOOK_SRC)
    _patch_context(mocker, tmp_path, skip_broken=True)

    manager = PluginManager.create()

    assert manager.pm.get_plugin("typoplug") is None
    assert manager.make_writer(HDLType.VERILOG).file_extension == ".v"
