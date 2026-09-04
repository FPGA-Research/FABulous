"""Provider descriptors for the plugin system.

Plugin authors import this module to declare what they contribute, so the
annotations naming the fabric model and the timing interface are deferred:
importing a descriptor must not drag in the generator stack behind them.
"""

from dataclasses import dataclass
from typing import TYPE_CHECKING

from fabulous.fabric_definition.define import HDLType

if TYPE_CHECKING:
    from collections.abc import Callable
    from pathlib import Path

    from fabulous.fabric_cad.timing_model.FABulous_timing_model_interface import (
        FABulousTimingModelInterface,
    )
    from fabulous.fabric_definition.fabric import Fabric
    from fabulous.fabric_generator.code_generator.code_generator import CodeGenerator

# PEP 695 aliases are evaluated lazily, so they may name the deferred imports.
type CodeGeneratorFactory = Callable[[], CodeGenerator]
type FabricParser = Callable[[Path], Fabric]
type PnRModelGenerator = Callable[
    [Fabric, FABulousTimingModelInterface | None], dict[str, str | bytes]
]


@dataclass(frozen=True, kw_only=True)
class CodeGeneratorProvider:
    """A code generator contributed by a plugin, keyed by `hdl_type`.

    Attributes
    ----------
    hdl_type : HDLType
        The HDL language this generator produces.
    factory : CodeGeneratorFactory
        Zero-argument factory returning a fresh generator (generators hold
        output state, so a new instance is created per use).
    name : str
        Human-readable provider name, used in diagnostics.
    """

    hdl_type: HDLType
    factory: CodeGeneratorFactory
    name: str


@dataclass(frozen=True, kw_only=True)
class ParserProvider:
    """A fabric-file parser contributed by a plugin, keyed by `suffix`.

    Attributes
    ----------
    suffix : str
        File suffix including the dot, e.g. `".csv"`.
    parse : FabricParser
        Callable parsing the file at the given path into a `Fabric`.
    name : str
        Human-readable provider name, used in diagnostics.
    """

    suffix: str
    parse: FabricParser
    name: str


@dataclass(frozen=True, kw_only=True)
class PnRModelProvider:
    """A place-and-route model generator contributed by a plugin.

    Providers are keyed by `tool`. `generate` returns the whole artifact set
    as a mapping of file name to file content, so each backend decides how
    many files it emits, what they are called, and how it embeds timing;
    the caller only writes the bytes out.

    Attributes
    ----------
    tool : str
        The place-and-route tool this backend models. Built-in backends use a
        `PnRTool` value; plugins may use any name not already registered.
    generate : PnRModelGenerator
        Build the model from a fabric. The second argument is a delay model,
        or `None` to generate an untimed model. Returns a mapping of file
        name, relative to the output directory, to file content.
    supports_timing : bool
        Whether `generate` honours a delay model. Passing one to a backend
        that does not is an error, never a silent untimed generation.
    name : str
        Human-readable provider name, used in diagnostics.
    """

    tool: str
    generate: PnRModelGenerator
    supports_timing: bool
    name: str
