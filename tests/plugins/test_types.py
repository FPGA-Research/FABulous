"""Tests for plugin provider descriptors and the error type."""

import dataclasses

import pytest

from fabulous.fabric_definition.define import HDLType
from fabulous.plugins.types import (
    CodeGeneratorProvider,
    ParserProvider,
    PluginError,
    PluginSettingsSpec,
)


def test_code_generator_provider_is_frozen() -> None:
    provider = CodeGeneratorProvider(HDLType.VERILOG, lambda: object(), "verilog")
    assert provider.name == "verilog"
    with pytest.raises(dataclasses.FrozenInstanceError):
        provider.name = "other"  # type: ignore[misc]


def test_parser_provider_holds_suffix_and_callable() -> None:
    provider = ParserProvider(".csv", lambda path: path, "csv")
    assert provider.suffix == ".csv"
    assert provider.parse("x") == "x"


def test_plugin_settings_spec_fields() -> None:
    spec = PluginSettingsSpec("demo", dict, "FAB_DEMO_")
    assert (spec.name, spec.model, spec.envPrefix) == ("demo", dict, "FAB_DEMO_")


def test_plugin_error_is_runtime_error() -> None:
    assert issubclass(PluginError, RuntimeError)
