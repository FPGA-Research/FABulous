"""Shared fixtures for plugin-system tests."""

import types

import pytest

from fabulous.fabric_definition.define import HDLType
from fabulous.plugins import hookspecs
from fabulous.plugins.types import (
    CodeGeneratorProvider,
    GdsFlowProvider,
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
        return [PnRModelProvider(tool, generate, supports_timing, name or tool)]

    module.fabulous_register_pnr_models = fabulous_register_pnr_models
    return module


@pytest.fixture
def fake_pnr_model_module() -> types.ModuleType:
    """A module exposing a place-and-route model hookimpl for the `fake` tool."""
    return make_pnr_model_module("fake")


def make_gds_flow_module(flow_cls: type) -> types.ModuleType:
    """Build a module exposing a GDS-flow hookimpl registering `flow_cls`.

    The provider derives its `meta.flow` key from the class name, so a test
    that needs a particular key registers a class of that name -- see
    `make_flow_class`.

    Parameters
    ----------
    flow_cls : type
        The flow class to register.

    Returns
    -------
    types.ModuleType
        A module registering one `GdsFlowProvider`.
    """
    module = types.ModuleType(f"fake_gds_flow_plugin_{flow_cls.__name__}")

    @hookspecs.hookimpl
    def fabulous_register_gds_flows() -> list[GdsFlowProvider]:
        return [GdsFlowProvider(flow_cls)]

    module.fabulous_register_gds_flows = fabulous_register_gds_flows
    return module


def make_flow_class(name: str, base: type | None = None, module: str = "") -> type:
    """Build a flow subclass called `name`, as a plugin's own class would be.

    Parameters
    ----------
    name : str
        Class name, which is also the `meta.flow` key it registers under.
    base : type | None
        Base to subclass. Defaults to None, which uses the built-in Verilog
        tile flow.
    module : str
        Value for the class's `__module__`, which is what distinguishes two
        same-named flows in a conflict message. Defaults to the caller's.

    Returns
    -------
    type
        The generated flow class.
    """
    from fabulous.fabric_generator.gds_generator.flows.tile_macro_flow import (
        FABulousTileVerilogMacroFlow,
    )

    namespace = {"__doc__": f"Test flow {name}."}
    if module:
        namespace["__module__"] = module
    return type(name, (base or FABulousTileVerilogMacroFlow,), namespace)
