"""Provider descriptors and the error type for the plugin system."""

from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING

from fabulous.fabric_definition.define import HDLType
from fabulous.fabric_definition.fabric import Fabric

if TYPE_CHECKING:
    from fabulous.fabric_generator.code_generator.code_generator import CodeGenerator


@dataclass(frozen=True)
class CodeGeneratorProvider:
    """A code generator contributed by a plugin, keyed by ``hdlType``.

    Attributes
    ----------
    hdlType : HDLType
        The HDL language this generator produces.
    factory : Callable[[], CodeGenerator]
        Zero-argument factory returning a fresh generator (generators hold
        output state, so a new instance is created per use).
    name : str
        Human-readable provider name, used in diagnostics.
    """

    hdlType: HDLType
    factory: "Callable[[], CodeGenerator]"
    name: str


@dataclass(frozen=True)
class ParserProvider:
    """A fabric-file parser contributed by a plugin, keyed by ``suffix``.

    Attributes
    ----------
    suffix : str
        File suffix including the dot, e.g. ``".csv"``.
    parse : Callable[[Path], Fabric]
        Callable parsing the file at the given path into a ``Fabric``.
    name : str
        Human-readable provider name, used in diagnostics.
    """

    suffix: str
    parse: Callable[[Path], Fabric]
    name: str


@dataclass(frozen=True)
class PluginSettingsSpec:
    """A pydantic settings model contributed by a plugin.

    Attributes
    ----------
    name : str
        Settings group name (used to look the instance up later).
    model : type
        A pydantic ``BaseModel`` subclass.
    envPrefix : str
        Environment-variable prefix, recorded for display.
    """

    name: str
    model: type
    envPrefix: str


class PluginError(RuntimeError):
    """Raised for plugin discovery, registration, or registry conflicts."""
