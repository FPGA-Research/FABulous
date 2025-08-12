"""
Test module for YosysJson class and related components using pytest.

This module provides comprehensive tests for the Yosys JSON parser,
including parsing of different HDL formats and netlist analysis methods.
"""

from pathlib import Path

import pytest
import pytest_mock

from FABulous.custom_exception import InvalidFileType
from FABulous.fabric_definition.Yosys_obj import (
    YosysJson,
)


def setup_mocks(monkeypatch: pytest.MonkeyPatch, json_data: dict) -> None:
    """Helper function to setup common mocks."""
    monkeypatch.setattr("subprocess.run", lambda cmd, check=False, capture_output=False: type("MockResult", (), {"stdout": b"mock output", "stderr": b""})())
    monkeypatch.setattr("json.load", lambda _: json_data)

    def mock_open_func(*_args: object, **_kwargs: object) -> object:
        return type(
            "MockFile",
            (),
            {
                "__enter__": lambda self: self,
                "__exit__": lambda _, *_args: None,
                "read": lambda _: "{}",
            },
        )()

    monkeypatch.setattr("builtins.open", mock_open_func)


def test_yosys_vhdl_json_initialization(mocker: pytest_mock.MockerFixture, tmp_path: Path) -> None:
    """Test YosysJson initialization with VHDL file."""
    # Mock external dependencies
    m = mocker.patch("subprocess.run", return_value=type("MockResult", (), {"stdout": b"mock output", "stderr": b""})())

    # Test with VHDL file
    (tmp_path / "file.json").write_text('{"modules": {"test": {}}}')
    (tmp_path / "file.vhdl").write_text("entity test is end entity;")
    YosysJson(tmp_path / "file.vhdl")

    assert m.call_count == 2
    assert "bin/ghdl" in str(m.call_args_list[0])
    assert "bin/yosys" in str(m.call_args_list[1])

def test_yosyst_sv_json_initialization(mocker: pytest_mock.MockerFixture, tmp_path: Path) -> None:
    """Test YosysJson initialization with VHDL file."""
    # Mock external dependencies
    m = mocker.patch("subprocess.run", return_value=type("MockResult", (), {"stdout": b"mock output", "stderr": b""})())

    # Test with VHDL file
    (tmp_path / "file.json").write_text("{}")
    (tmp_path / "file.sv").touch()
    YosysJson(tmp_path / "file.sv")

    m.assert_called_once()
    assert "read_verilog -sv" in str(m.call_args)


def test_yosys_json_initialization(mocker: pytest_mock.MockerFixture, tmp_path: Path) -> None:
    """Test YosysJson initialization with VHDL file."""
    # Mock external dependencies
    m = mocker.patch("subprocess.run", return_value=type("MockResult", (), {"stdout": b"mock output", "stderr": b""})())

    # Test with VHDL file
    (tmp_path / "file.json").write_text("{}")

    fakePath = tmp_path / "file.v"
    fakePath.touch()
    fakePath.with_suffix(".json").touch()
    YosysJson(fakePath)

    m.assert_called_once()
    assert "read_verilog" in str(m.call_args)


def test_yosys_json_file_not_exists(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """Test YosysJson with unsupported file type."""
    setup_mocks(monkeypatch, {})
    fakePath = tmp_path / "file.txt"
    with pytest.raises(FileNotFoundError, match="does not exist"):
        YosysJson(fakePath)


def test_yosys_json_unsupported_file_type(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """Test YosysJson with unsupported file type."""
    setup_mocks(monkeypatch, {})
    fakePath = tmp_path / "file.txt"
    fakePath.touch()
    with pytest.raises(InvalidFileType, match="Unsupported HDL file type"):
        YosysJson(fakePath)


def test_get_top_module(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
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
    fakePath = tmp_path / "test_file.v"
    fakePath.touch()
    fakePath.with_suffix(".json").touch()
    yosys_json = YosysJson(fakePath)
    top_module = yosys_json.getTopModule()

    assert "top" in top_module.attributes
    assert top_module.attributes["top"] == 1


def test_get_top_module_no_top(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
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
    fakePath = tmp_path / "test_file.v"
    fakePath.touch()
    fakePath.with_suffix(".json").touch()
    yosys_json = YosysJson(fakePath)
    with pytest.raises(ValueError, match="No top module found"):
        _ = yosys_json.getTopModule()


def test_getNetPortSrcSinks(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
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
    fakePath = tmp_path / "test_file.v"
    fakePath.touch()
    fakePath.with_suffix(".json").touch()
    yosys_json = YosysJson(fakePath)

    assert yosys_json.getNetPortSrcSinks(2) == (("A", "Y"), [("B", "A")])
