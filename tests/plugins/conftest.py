"""Shared fixtures for plugin-system tests."""

from dataclasses import dataclass
from pathlib import Path

import pytest

from fabulous.fabric_cad.timing_model.FABulous_timing_model_interface import (
    FABulousTimingModelInterface,
)
from fabulous.fabric_cad.timing_model.models import TimingModelTarget
from fabulous.fabric_definition.define import HDLType
from fabulous.fabric_definition.fabric import Fabric
from fabulous.fabric_generator.code_generator.code_generator_Verilog import (
    VerilogCodeGenerator,
)
from fabulous.plugins import hookspecs
from fabulous.plugins.types import (
    CodeGeneratorProvider,
    ParserProvider,
    PnRModelProvider,
)


class _FakeWriter(VerilogCodeGenerator):
    hdl_type = HDLType.SYSTEM_VERILOG
    file_extension = ".fake"


def parse_fake_fabric(path: Path) -> Fabric:
    """Parse any file into an empty fabric rooted beside it."""
    return Fabric(fabric_dir=path.parent)


@dataclass(frozen=True, eq=False)
class CodegenPlugin:
    """A plugin registering one code generator for `hdl_type`."""

    hdl_type: HDLType
    name: str

    @hookspecs.hookimpl
    def fabulous_register_code_generators(self) -> list[CodeGeneratorProvider]:
        """Register the fake writer under `hdl_type`."""
        return [
            CodeGeneratorProvider(
                hdl_type=self.hdl_type, factory=_FakeWriter, name=self.name
            )
        ]


@dataclass(frozen=True, eq=False)
class ParserPlugin:
    """A plugin registering `parse_fake_fabric` for `suffix`."""

    suffix: str
    name: str

    @hookspecs.hookimpl
    def fabulous_register_parsers(self) -> list[ParserProvider]:
        """Register the fake parser under `suffix`."""
        return [
            ParserProvider(suffix=self.suffix, parse=parse_fake_fabric, name=self.name)
        ]


@dataclass(frozen=True, eq=False)
class PnRModelPlugin:
    """A plugin registering one place-and-route model for `tool`."""

    tool: str
    supports_timing: bool
    name: str

    def generate(
        self,
        _fabric: Fabric,
        delay_model: FABulousTimingModelInterface | None,
        _target: TimingModelTarget,
    ) -> dict[str, str | bytes]:
        """Report whether a delay model was passed."""
        return {f"{self.tool}.txt": f"timed={delay_model is not None}"}

    @hookspecs.hookimpl
    def fabulous_register_pnr_models(self) -> list[PnRModelProvider]:
        """Register `generate` under `tool`."""
        return [
            PnRModelProvider(
                tool=self.tool,
                generate=self.generate,
                supports_timing=self.supports_timing,
                name=self.name,
            )
        ]


def make_codegen_plugin(hdl_type: HDLType, name: str) -> CodegenPlugin:
    """Build a plugin registering one code generator for `hdl_type`.

    Parameters
    ----------
    hdl_type : HDLType
        The HDL type the provider claims.
    name : str
        Provider name used in diagnostics.

    Returns
    -------
    CodegenPlugin
        A plugin registering one `CodeGeneratorProvider`.
    """
    return CodegenPlugin(hdl_type=hdl_type, name=name)


def make_parser_plugin(suffix: str, name: str) -> ParserPlugin:
    """Build a plugin registering one parser for `suffix`.

    Parameters
    ----------
    suffix : str
        The file suffix the provider claims.
    name : str
        Provider name used in diagnostics.

    Returns
    -------
    ParserPlugin
        A plugin registering one `ParserProvider`.
    """
    return ParserPlugin(suffix=suffix, name=name)


def make_pnr_model_plugin(
    tool: str, supports_timing: bool = True, name: str | None = None
) -> PnRModelPlugin:
    """Build a plugin registering one place-and-route model for `tool`.

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
    PnRModelPlugin
        A plugin registering one `PnRModelProvider`.
    """
    return PnRModelPlugin(tool=tool, supports_timing=supports_timing, name=name or tool)


@pytest.fixture
def fake_codegen_plugin() -> CodegenPlugin:
    """A plugin exposing a code-generator hookimpl for one fake HDLType."""
    return make_codegen_plugin(HDLType.SYSTEM_VERILOG, "fake")


@pytest.fixture
def fake_parser_plugin() -> ParserPlugin:
    """A plugin exposing a parser hookimpl for the `.fake` suffix."""
    return make_parser_plugin(".fake", "fake")


@pytest.fixture
def fake_pnr_model_plugin() -> PnRModelPlugin:
    """A plugin exposing a place-and-route model hookimpl for the `fake` tool."""
    return make_pnr_model_plugin("fake")
