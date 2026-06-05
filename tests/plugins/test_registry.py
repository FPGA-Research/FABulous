"""Registry folding and factory-method resolution semantics."""

import types
from pathlib import Path

import pytest

from fabulous.fabric_definition.define import HDLType
from fabulous.plugins import hookspecs
from fabulous.plugins.manager import PluginManager
from fabulous.plugins.types import CodeGeneratorProvider, PluginError


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


def test_duplicate_code_generator_key_raises_naming_both() -> None:
    class _W:
        file_extension = ".v"

    def _make_module(provider_name: str) -> types.ModuleType:
        module = types.ModuleType(f"dup_{provider_name}")

        @hookspecs.hookimpl
        def fabulous_register_code_generators() -> list[CodeGeneratorProvider]:
            return [CodeGeneratorProvider(HDLType.VERILOG, _W, provider_name)]

        module.fabulous_register_code_generators = fabulous_register_code_generators
        return module

    manager = PluginManager()
    manager.pm.register(_make_module("alpha"), name="alpha")
    manager.pm.register(_make_module("beta"), name="beta")
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
