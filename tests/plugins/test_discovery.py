"""Discovery of built-in, directory, entry-point and session plugins."""

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

PARSER_PLUGIN_SRC = """
from fabulous.plugins import PLUGIN_API_VERSION, hookimpl
from fabulous.plugins.types import ParserProvider

FABULOUS_PLUGIN_API = PLUGIN_API_VERSION


@hookimpl
def fabulous_register_parsers():
    return [ParserProvider(suffix="{suffix}", parse=lambda path: path, name="{name}")]
"""

# Every way a plugin can be broken, paired with the id its failure names.
BROKEN_PLUGIN_SRCS = [
    pytest.param("raise ImportError('boom')\n", id="raises-on-import"),
    pytest.param("FABULOUS_PLUGIN_API = -1\n", id="incompatible-api"),
    pytest.param("x = 1\n", id="missing-api-declaration"),
    pytest.param(
        "from fabulous.plugins import PLUGIN_API_VERSION, hookimpl\n"
        "FABULOUS_PLUGIN_API = PLUGIN_API_VERSION\n"
        "@hookimpl\n"
        "def fabulous_register_code_generator():\n"
        "    return []\n",
        id="misspelled-hook",
    ),
    pytest.param(
        "from fabulous.plugins import PLUGIN_API_VERSION, hookimpl\n"
        "FABULOUS_PLUGIN_API = PLUGIN_API_VERSION\n"
        "@hookimpl\n"
        "def fabulous_register_code_generators():\n"
        "    raise RuntimeError('boom')\n",
        id="raises-in-hook",
    ),
]


def _write_dir_plugin(base: Path, name: str, src: str) -> Path:
    pkg = base / name
    pkg.mkdir(parents=True)
    (pkg / "__init__.py").write_text(src)
    return pkg


def _write_parser_plugin(base: Path, name: str, suffix: str) -> Path:
    return _write_dir_plugin(
        base, name, PARSER_PLUGIN_SRC.format(suffix=suffix, name=name)
    )


def _patch_context(
    mocker: MockerFixture, plugin_dir: Path, *, skip_broken: bool = False
) -> None:
    """Point `create()` at `plugin_dir` for directory-plugin discovery."""
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
    _write_parser_plugin(tmp_path, "alpha", ".a")
    _patch_context(mocker, tmp_path)
    manager = PluginManager.create()
    assert manager.make_parser(Path("fabric.a")) is not None


def test_dir_scan_is_sorted(tmp_path: Path, mocker: MockerFixture) -> None:
    _write_parser_plugin(tmp_path, "bbb", ".b")
    _write_parser_plugin(tmp_path, "aaa", ".a")
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
    # An absent plugin directory discovers nothing.
    _patch_context(mocker, tmp_path / "plugins")
    manager = PluginManager.create()
    assert manager.make_parser(Path("fabric.ep")) is not None


def test_session_plugin_dir(tmp_path: Path, mocker: MockerFixture) -> None:
    _write_parser_plugin(tmp_path, "sess", ".s")
    _patch_context(mocker, tmp_path / "plugins")
    manager = PluginManager.create(extra_plugins=(str(tmp_path / "sess"),))
    assert manager.make_parser(Path("fabric.s")) is not None


@pytest.mark.parametrize("src", BROKEN_PLUGIN_SRCS)
def test_broken_plugin_strict_aborts_naming_it(
    src: str, tmp_path: Path, mocker: MockerFixture
) -> None:
    """Without `skip_broken`, any broken plugin aborts discovery by name."""
    _write_dir_plugin(tmp_path, "broke", src)
    _patch_context(mocker, tmp_path, skip_broken=False)

    with pytest.raises(PluginError) as exc:
        PluginManager.create()

    assert "broke" in str(exc.value)


@pytest.mark.parametrize("src", BROKEN_PLUGIN_SRCS)
def test_broken_plugin_lenient_drops_only_it(
    src: str, tmp_path: Path, mocker: MockerFixture
) -> None:
    """Under `skip_broken`, only the broken plugin is dropped.

    The provider hooks aggregate across plugins, so a raising implementation
    would otherwise empty the registry it contributes to and take the built-in
    generators with it.
    """
    _write_dir_plugin(tmp_path, "broke", src)
    _patch_context(mocker, tmp_path, skip_broken=True)

    manager = PluginManager.create()

    assert manager.pm.get_plugin("broke") is None
    assert manager.make_writer(HDLType.VERILOG).file_extension == ".v"


def test_package_plugin_resolves_relative_import(
    tmp_path: Path, mocker: MockerFixture
) -> None:
    """A multi-file plugin package may import its own submodules.

    Executing the module without a `sys.modules` entry leaves the relative
    import with no parent package to resolve against.
    """
    pkg = _write_dir_plugin(
        tmp_path,
        "multi",
        "from fabulous.plugins import PLUGIN_API_VERSION\n"
        "from .provider import fabulous_register_parsers\n"
        "FABULOUS_PLUGIN_API = PLUGIN_API_VERSION\n",
    )
    (pkg / "provider.py").write_text(
        PARSER_PLUGIN_SRC.format(suffix=".m", name="multi")
    )
    _patch_context(mocker, tmp_path)

    manager = PluginManager.create()

    assert manager.make_parser(Path("fabric.m")) is not None


def test_failed_load_leaves_no_sys_modules_entry(
    tmp_path: Path, mocker: MockerFixture
) -> None:
    """A half-executed plugin must not shadow a real module of the same name."""
    _write_dir_plugin(tmp_path, "halfdead", "raise ImportError('boom')")
    _patch_context(mocker, tmp_path, skip_broken=True)

    PluginManager.create()

    assert "halfdead" not in sys.modules


def test_skip_broken_defaults_to_the_setting(
    tmp_path: Path, mocker: MockerFixture
) -> None:
    """`create(skip_broken=None)` reads `skip_broken_plugins` off the context."""
    _write_dir_plugin(tmp_path, "broke", "raise ImportError('boom')")
    _patch_context(mocker, tmp_path, skip_broken=True)

    manager = PluginManager.create(skip_broken=None)

    assert manager.pm.get_plugin("broke") is None
