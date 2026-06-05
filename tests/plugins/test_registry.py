"""Registry folding and resolution semantics."""

import types

import pytest

from fabulous.fabric_definition.define import HDLType
from fabulous.plugins import hookspecs
from fabulous.plugins.manager import FABulousPluginManager
from fabulous.plugins.types import CodeGeneratorProvider, PluginError


def test_resolves_registered_code_generator(
    fake_codegen_module: types.ModuleType,
) -> None:
    manager = FABulousPluginManager()
    manager.pm.register(fake_codegen_module, name="fake_codegen")
    manager.build_registries()
    writer = manager.get_code_generator(HDLType.SYSTEM_VERILOG)
    assert writer.fileExtension == ".fake"


def test_resolves_registered_parser(fake_parser_module: types.ModuleType) -> None:
    manager = FABulousPluginManager()
    manager.pm.register(fake_parser_module, name="fake_parser")
    manager.build_registries()
    parse = manager.get_parser(".fake")
    assert parse("path") == "path"


def test_duplicate_code_generator_key_raises_naming_both() -> None:
    class _W:
        fileExtension = ".v"

    def _make_module(provider_name: str) -> types.ModuleType:
        module = types.ModuleType(f"dup_{provider_name}")

        @hookspecs.hookimpl
        def fabulous_register_code_generators() -> list[CodeGeneratorProvider]:
            return [CodeGeneratorProvider(HDLType.VERILOG, _W, provider_name)]

        module.fabulous_register_code_generators = fabulous_register_code_generators
        return module

    manager = FABulousPluginManager()
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
    manager = FABulousPluginManager()
    manager.pm.register(fake_codegen_module, name="fake_codegen")
    manager.build_registries()
    with pytest.raises(PluginError) as exc:
        manager.get_code_generator(HDLType.VHDL)
    assert "system_verilog" in str(exc.value)


def test_missing_parser_raises(fake_parser_module: types.ModuleType) -> None:
    manager = FABulousPluginManager()
    manager.pm.register(fake_parser_module, name="fake_parser")
    manager.build_registries()
    with pytest.raises(PluginError):
        manager.get_parser(".csv")
