"""Provider descriptors and the error type for the plugin system."""

from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from fabulous.fabric_cad.timing_model.FABulous_timing_model_interface import (
    FABulousTimingModelInterface,
)
from fabulous.fabric_definition.define import HDLType
from fabulous.fabric_definition.fabric import Fabric
from fabulous.fabric_generator.code_generator.code_generator import CodeGenerator


@dataclass(frozen=True)
class CodeGeneratorProvider:
    """A code generator contributed by a plugin, keyed by `hdl_type`.

    Attributes
    ----------
    hdl_type : HDLType
        The HDL language this generator produces.
    factory : Callable[[], CodeGenerator]
        Zero-argument factory returning a fresh generator (generators hold
        output state, so a new instance is created per use).
    name : str
        Human-readable provider name, used in diagnostics.
    """

    hdl_type: HDLType
    factory: Callable[[], CodeGenerator]
    name: str


@dataclass(frozen=True)
class ParserProvider:
    """A fabric-file parser contributed by a plugin, keyed by `suffix`.

    Attributes
    ----------
    suffix : str
        File suffix including the dot, e.g. `".csv"`.
    parse : Callable[[Path], Fabric]
        Callable parsing the file at the given path into a `Fabric`.
    name : str
        Human-readable provider name, used in diagnostics.
    """

    suffix: str
    parse: Callable[[Path], Fabric]
    name: str


@dataclass(frozen=True)
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
    generate : Callable[[Fabric, FABulousTimingModelInterface | None], dict[str, str | bytes]]
        Build the model from a fabric. The second argument is a delay model,
        or `None` to generate an untimed model. Returns a mapping of file
        name, relative to the output directory, to file content.
    supports_timing : bool
        Whether `generate` honours a delay model. Passing one to a backend
        that does not is an error, never a silent untimed generation.
    name : str
        Human-readable provider name, used in diagnostics.
    """  # noqa: E501 - the Callable signature does not usefully wrap

    tool: str
    generate: Callable[
        [Fabric, FABulousTimingModelInterface | None], dict[str, str | bytes]
    ]
    supports_timing: bool
    name: str


class PluginError(RuntimeError):
    """Raised for plugin discovery, registration, or registry conflicts."""
