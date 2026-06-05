"""Shared fixtures for plugin-system tests."""

import types

import pytest

from fabulous.fabric_definition.define import HDLType
from fabulous.plugins import hookspecs
from fabulous.plugins.types import CodeGeneratorProvider, ParserProvider


class _FakeWriter:
    fileExtension = ".fake"


@pytest.fixture
def fake_codegen_module() -> types.ModuleType:
    """A module exposing a code-generator hookimpl for one fake HDLType."""
    module = types.ModuleType("fake_codegen_plugin")

    @hookspecs.hookimpl
    def fabulous_register_code_generators() -> list[CodeGeneratorProvider]:
        return [CodeGeneratorProvider(HDLType.SYSTEM_VERILOG, _FakeWriter, "fake")]

    module.fabulous_register_code_generators = fabulous_register_code_generators
    return module


@pytest.fixture
def fake_parser_module() -> types.ModuleType:
    """A module exposing a parser hookimpl for the ``.fake`` suffix."""
    module = types.ModuleType("fake_parser_plugin")

    @hookspecs.hookimpl
    def fabulous_register_parsers() -> list[ParserProvider]:
        return [ParserProvider(".fake", lambda path: path, "fake")]

    module.fabulous_register_parsers = fabulous_register_parsers
    return module
