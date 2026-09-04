"""Tests for plugin provider descriptors and the error type."""

import dataclasses

import pytest

from fabulous.custom_exception import PluginError
from fabulous.fabric_definition.define import HDLType
from fabulous.plugins.types import CodeGeneratorProvider, ParserProvider


def test_code_generator_provider_is_frozen() -> None:
    provider = CodeGeneratorProvider(
        hdl_type=HDLType.VERILOG, factory=lambda: object(), name="verilog"
    )
    assert provider.name == "verilog"
    with pytest.raises(dataclasses.FrozenInstanceError):
        provider.name = "other"  # type: ignore[misc]


def test_parser_provider_holds_suffix_and_callable() -> None:
    provider = ParserProvider(suffix=".csv", parse=lambda path: path, name="csv")
    assert provider.suffix == ".csv"
    assert provider.parse("x") == "x"


def test_plugin_error_is_runtime_error() -> None:
    assert issubclass(PluginError, RuntimeError)
