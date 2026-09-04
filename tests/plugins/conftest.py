"""Shared fixtures for plugin-system tests."""

import types

import pytest

from fabulous.fabric_definition.define import HDLType
from fabulous.plugins import hookspecs
from fabulous.plugins.types import (
    CodeGeneratorProvider,
    ParserProvider,
    PnRModelProvider,
)


class _FakeWriter:
    file_extension = ".fake"


@pytest.fixture
def fake_codegen_module() -> types.ModuleType:
    """A module exposing a code-generator hookimpl for one fake HDLType."""
    module = types.ModuleType("fake_codegen_plugin")

    @hookspecs.hookimpl
    def fabulous_register_code_generators() -> list[CodeGeneratorProvider]:
        return [
            CodeGeneratorProvider(
                hdl_type=HDLType.SYSTEM_VERILOG, factory=_FakeWriter, name="fake"
            )
        ]

    module.fabulous_register_code_generators = fabulous_register_code_generators
    return module


@pytest.fixture
def fake_parser_module() -> types.ModuleType:
    """A module exposing a parser hookimpl for the `.fake` suffix."""
    module = types.ModuleType("fake_parser_plugin")

    @hookspecs.hookimpl
    def fabulous_register_parsers() -> list[ParserProvider]:
        return [ParserProvider(suffix=".fake", parse=lambda path: path, name="fake")]

    module.fabulous_register_parsers = fabulous_register_parsers
    return module


def make_codegen_module(hdl_type: HDLType, name: str) -> types.ModuleType:
    """Build a module registering one code generator for `hdl_type`.

    Parameters
    ----------
    hdl_type : HDLType
        The HDL type the provider claims.
    name : str
        Provider name used in diagnostics.

    Returns
    -------
    types.ModuleType
        A module registering one `CodeGeneratorProvider`.
    """
    module = types.ModuleType(f"fake_codegen_plugin_{name}")

    @hookspecs.hookimpl
    def fabulous_register_code_generators() -> list[CodeGeneratorProvider]:
        return [
            CodeGeneratorProvider(hdl_type=hdl_type, factory=_FakeWriter, name=name)
        ]

    module.fabulous_register_code_generators = fabulous_register_code_generators
    return module


def make_parser_module(suffix: str, name: str) -> types.ModuleType:
    """Build a module registering one parser for `suffix`.

    Parameters
    ----------
    suffix : str
        The file suffix the provider claims.
    name : str
        Provider name used in diagnostics.

    Returns
    -------
    types.ModuleType
        A module registering one `ParserProvider`.
    """
    module = types.ModuleType(f"fake_parser_plugin_{name}")

    @hookspecs.hookimpl
    def fabulous_register_parsers() -> list[ParserProvider]:
        return [ParserProvider(suffix=suffix, parse=lambda path: path, name=name)]

    module.fabulous_register_parsers = fabulous_register_parsers
    return module


def make_pnr_model_module(
    tool: str, supports_timing: bool = True, name: str | None = None
) -> types.ModuleType:
    """Build a module exposing a place-and-route model hookimpl for `tool`.

    Parameters
    ----------
    tool : str
        The place-and-route tool the provider claims.
    supports_timing : bool
        Whether the provider declares delay-model support. Defaults to True.
    name : str | None
        Provider name used in diagnostics. Defaults to None, which reuses
        `tool`.

    Returns
    -------
    types.ModuleType
        A module registering one `PnRModelProvider`.
    """
    module = types.ModuleType(f"fake_pnr_plugin_{tool}")

    def generate(_fabric: object, delay_model: object) -> dict[str, str | bytes]:
        return {f"{tool}.txt": f"timed={delay_model is not None}"}

    @hookspecs.hookimpl
    def fabulous_register_pnr_models() -> list[PnRModelProvider]:
        return [
            PnRModelProvider(
                tool=tool,
                generate=generate,
                supports_timing=supports_timing,
                name=name or tool,
            )
        ]

    module.fabulous_register_pnr_models = fabulous_register_pnr_models
    return module


@pytest.fixture
def fake_pnr_model_module() -> types.ModuleType:
    """A module exposing a place-and-route model hookimpl for the `fake` tool."""
    return make_pnr_model_module("fake")
