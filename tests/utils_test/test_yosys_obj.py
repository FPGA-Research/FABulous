"""
Test module for YosysJson class and related components using pytest.

This module provides comprehensive tests for the Yosys JSON parser,
including parsing of different HDL formats and netlist analysis methods.
"""

from pathlib import Path

import pytest

from FABulous.fabric_definition.Yosys_obj import (
    YosysJson,
)


def setup_mocks(monkeypatch, json_data):
    """Helper function to setup common mocks."""
    monkeypatch.setattr("FABulous.fabric_definition.Yosys_obj.check_if_application_exists", lambda _: "yosys")
    monkeypatch.setattr("subprocess.run", lambda cmd, check=False: type("MockResult", (), {})())
    monkeypatch.setattr("json.load", lambda a: json_data)

    def mock_open_func(*args, **kwargs):
        return type(
            "MockFile",
            (),
            {
                "__enter__": lambda self: self,
                "__exit__": lambda self, *args: None,
                "read": lambda self: "{}",
            },
        )()

    monkeypatch.setattr("builtins.open", mock_open_func)


def test_yosys_vhdl_json_initialization(mocker, tmp_path):
    """Test YosysJson initialization with VHDL file."""
    # Mock external dependencies
    m = mocker.patch("subprocess.run", return_value=None)

    # Test with VHDL file
    with open(tmp_path / "file.json", "w") as f:
        f.write("{}")

    YosysJson(tmp_path / "file.vhdl")

    m.assert_called_once()
    assert "ghdl" in str(m.call_args)


def test_yosyst_sv_json_initialization(mocker, tmp_path):
    """Test YosysJson initialization with VHDL file."""
    # Mock external dependencies
    m = mocker.patch("subprocess.run", return_value=None)

    # Test with VHDL file
    with open(tmp_path / "file.json", "w") as f:
        f.write("{}")

    YosysJson(tmp_path / "file.sv")

    m.assert_called_once()
    assert "read_verilog -sv" in str(m.call_args)


def test_yosys_json_initialization(mocker, tmp_path):
    """Test YosysJson initialization with VHDL file."""
    # Mock external dependencies
    m = mocker.patch("subprocess.run", return_value=None)

    # Test with VHDL file
    with open(tmp_path / "file.json", "w") as f:
        f.write("{}")

    YosysJson(tmp_path / "file.v")

    m.assert_called_once()
    assert "read_verilog" in str(m.call_args)


def test_yosys_json_unsupported_file_type(monkeypatch):
    """Test YosysJson with unsupported file type."""
    monkeypatch.setattr("FABulous.fabric_definition.Yosys_obj.check_if_application_exists", lambda _: "yosys")

    with pytest.raises(ValueError, match="Unsupported HDL file type"):
        YosysJson(Path("/test/file.txt"))


def test_get_top_module(monkeypatch):
    """Test getTopModule method."""

    json_data = {
        "creator": "Yosys 0.33",
        "modules": {
            "module1": {
                "attributes": {"top": 1},
                "parameter_default_values": {},
                "ports": {},
                "cells": {},
                "memories": {},
                "netnames": {},
            }
        },
        "models": {},
    }

    setup_mocks(monkeypatch, json_data)

    yosys_json = YosysJson(Path("/test/file.v"))
    top_module = yosys_json.getTopModule()

    assert "top" in top_module.attributes
    assert top_module.attributes["top"] == 1


def test_get_top_module_no_top(monkeypatch):
    """Test getTopModule method."""

    json_data = {
        "creator": "Yosys 0.33",
        "modules": {
            "module1": {
                "attributes": {},
                "parameter_default_values": {},
                "ports": {},
                "cells": {},
                "memories": {},
                "netnames": {},
            }
        },
        "models": {},
    }

    setup_mocks(monkeypatch, json_data)

    yosys_json = YosysJson(Path("/test/file.v"))
    with pytest.raises(ValueError, match="No top module found"):
        _ = yosys_json.getTopModule()


def test_getNetPortSrcSinks(monkeypatch):
    json_data = {
        "creator": "Yosys 0.33",
        "modules": {
            "module1": {
                "attributes": {},
                "parameter_default_values": {},
                "ports": {},
                "cells": {
                    "A": {
                        "hide_name": "",
                        "attributes": {},
                        "parameters": {},
                        "type": "DFF",
                        "port_directions": {"A": "input", "Y": "output"},
                        "connections": {
                            "A": [1],
                            "Y": [2],
                        },
                    },
                    "B": {
                        "hide_name": "",
                        "attributes": {},
                        "parameters": {},
                        "type": "DFF",
                        "port_directions": {"A": "input", "Y": "output"},
                        "connections": {
                            "A": [2],
                            "Y": [3],
                        },
                    },
                },
                "memories": {},
                "netnames": {},
            }
        },
        "models": {},
    }

    setup_mocks(monkeypatch, json_data)

    yosys_json = YosysJson(Path("/test/file.v"))

    assert yosys_json.getNetPortSrcSinks(2) == (("A", "Y"), [("B", "A")])
