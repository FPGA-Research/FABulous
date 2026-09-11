"""Registry folding and factory-method resolution semantics."""

import types
from collections.abc import Callable
from pathlib import Path

import pytest

from fabulous.custom_exception import PluginError
from fabulous.fabric_definition.define import HDLType
from fabulous.plugins.manager import PluginManager
from tests.plugins.conftest import (
    make_codegen_module,
    make_parser_module,
    make_pnr_model_module,
)


def test_resolves_registered_code_generator(
    fake_codegen_module: types.ModuleType,
) -> None:
    manager = PluginManager()
    manager.pm.register(fake_codegen_module, name="fake_codegen")
    manager.build_registries()
    writer = manager.make_writer(HDLType.SYSTEM_VERILOG)
    assert writer.file_extension == ".fake"


def test_resolves_registered_parser(fake_parser_module: types.ModuleType) -> None:
    manager = PluginManager()
    manager.pm.register(fake_parser_module, name="fake_parser")
    manager.build_registries()
    parse = manager.make_parser(Path("fabric.fake"))
    assert parse("path") == "path"


@pytest.mark.parametrize(
    "make_module",
    [
        lambda name: make_codegen_module(HDLType.VERILOG, name),
        lambda name: make_parser_module(".dup", name),
        lambda name: make_pnr_model_module("dup", name=name),
    ],
    ids=["code_generator", "parser", "pnr_model"],
)
def test_duplicate_key_raises_naming_both(
    make_module: Callable[[str], types.ModuleType],
) -> None:
    """Two providers claiming one key is a conflict, whichever registry it is."""
    manager = PluginManager()
    manager.pm.register(make_module("alpha"), name="alpha")
    manager.pm.register(make_module("beta"), name="beta")

    with pytest.raises(PluginError) as exc:
        manager.build_registries()

    message = str(exc.value)
    assert "alpha" in message
    assert "beta" in message


def test_missing_code_generator_lists_available(
    fake_codegen_module: types.ModuleType,
) -> None:
    manager = PluginManager()
    manager.pm.register(fake_codegen_module, name="fake_codegen")
    manager.build_registries()
    with pytest.raises(PluginError) as exc:
        manager.make_writer(HDLType.VHDL)
    assert "system_verilog" in str(exc.value)


def test_missing_parser_raises(fake_parser_module: types.ModuleType) -> None:
    manager = PluginManager()
    manager.pm.register(fake_parser_module, name="fake_parser")
    manager.build_registries()
    with pytest.raises(PluginError):
        manager.make_parser(Path("fabric.csv"))
