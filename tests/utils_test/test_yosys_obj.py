"""Test module for YosysJson class and related components using pytest.

This module provides comprehensive tests for the Yosys JSON parser, including parsing of
different HDL formats and netlist analysis methods.

Only `subprocess.run` is mocked: the netlist Yosys would emit is written to the
companion `.json` file, so `YosysJson` parses real JSON from disk.
"""

import json
from pathlib import Path

import pytest
from pytest_mock import MockerFixture, MockType

from fabulous.custom_exception import InvalidFileType
from fabulous.fabric_definition.yosys_obj import YosysJson
from fabulous.fabulous_settings import get_context


def _module(attributes: dict, cells: dict | None = None) -> dict:
    """Return a Yosys JSON module entry with the given attributes and cells."""
    return {
        "attributes": attributes,
        "parameter_default_values": {},
        "ports": {},
        "cells": cells or {},
        "memories": {},
        "netnames": {},
    }


def _mock_tools(mocker: MockerFixture, stdout: str = "") -> MockType:
    """Mock the external tool process, which always succeeds."""
    return mocker.patch(
        "subprocess.run",
        return_value=mocker.Mock(stdout=stdout, stderr="", returncode=0),
    )


def _load(mocker: MockerFixture, tmp_path: Path, modules: dict) -> YosysJson:
    """Parse a Verilog file whose Yosys netlist holds `modules`."""
    _mock_tools(mocker)
    src = tmp_path / "test_file.v"
    src.touch()
    src.with_suffix(".json").write_text(
        json.dumps({"creator": "Yosys 0.33", "modules": modules, "models": {}})
    )
    return YosysJson(src)


def _yosys_call(mocker: MockerFixture, verilog: Path, json_file: Path) -> object:
    """Return the expected `subprocess.run` call converting `verilog` to JSON."""
    return mocker.call(
        [
            str(get_context().yosys_path),
            "-q",
            f"-p read_verilog -sv {verilog}; hierarchy -auto-top; proc -noopt; "
            f"write_json -compat-int {json_file}",
        ],
        input="",
        text=True,
        capture_output=True,
        check=False,
    )


@pytest.mark.parametrize("suffix", [".v", ".sv"])
def test_verilog_is_read_by_yosys_directly(
    mocker: MockerFixture, tmp_path: Path, suffix: str
) -> None:
    """Verilog and SystemVerilog go straight to Yosys, one call, no GHDL."""
    run = _mock_tools(mocker)
    src = tmp_path / f"file{suffix}"
    src.touch()
    src.with_suffix(".json").write_text('{"modules": {"file": {}}}')

    yosys_json = YosysJson(src)

    assert run.call_args_list == [_yosys_call(mocker, src, src.with_suffix(".json"))]
    assert list(yosys_json.modules) == ["file"]


def test_vhdl_is_elaborated_by_ghdl_then_read_by_yosys(
    mocker: MockerFixture, tmp_path: Path
) -> None:
    """VHDL is elaborated to Verilog by GHDL, whose output Yosys then reads."""
    run = _mock_tools(mocker, stdout="module file; endmodule\n")
    src = tmp_path / "file.vhdl"
    src.write_text("entity file is end entity;")
    src.with_suffix(".json").write_text('{"modules": {"file": {}}}')

    YosysJson(src)

    ghdl_call = mocker.call(
        [
            str(get_context().ghdl_path),
            "--synth",
            "--std=08",
            "--out=verilog",
            mocker.ANY,  # per-invocation stub package in a temp file
            str(get_context().models_pack),
            str(src),
            "-e",
            "file",
        ],
        input="",
        text=True,
        capture_output=True,
        check=False,
    )
    assert run.call_args_list == [
        ghdl_call,
        _yosys_call(mocker, src.with_suffix(".v"), src.with_suffix(".json")),
    ]
    assert src.with_suffix(".v").read_text() == "module file; endmodule\n"


def test_yosys_json_file_not_exists(tmp_path: Path) -> None:
    """A missing HDL file is rejected before any tool runs."""
    with pytest.raises(FileNotFoundError, match="does not exist"):
        YosysJson(tmp_path / "file.txt")


def test_yosys_json_unsupported_file_type(tmp_path: Path) -> None:
    """Test YosysJson with unsupported file type."""
    fake_path = tmp_path / "file.txt"
    fake_path.touch()
    with pytest.raises(InvalidFileType, match="Unsupported HDL file type"):
        YosysJson(fake_path)


@pytest.mark.parametrize(
    ("modules", "expected_name"),
    [
        pytest.param({"module1": _module({"top": 1})}, "module1", id="top"),
        pytest.param(
            {"blackbox_mod": _module({"blackbox": 1})},
            "blackbox_mod",
            id="blackbox_fallback",
        ),
        pytest.param(
            {
                "blackbox_mod": _module({"blackbox": 1}),
                "top_mod": _module({"top": 1}),
            },
            "top_mod",
            id="prefers_top_over_earlier_blackbox",
        ),
    ],
)
def test_get_top_module(
    mocker: MockerFixture, tmp_path: Path, modules: dict, expected_name: str
) -> None:
    """The `top` module wins; a blackbox module is the fallback."""
    yosys_json = _load(mocker, tmp_path, modules)

    module_name, module = yosys_json.getTopModule()

    assert module_name == expected_name
    assert module is yosys_json.modules[expected_name]


def test_get_top_module_no_top(mocker: MockerFixture, tmp_path: Path) -> None:
    """A netlist with neither a top nor a blackbox module has no top module."""
    yosys_json = _load(mocker, tmp_path, {"module1": _module({})})
    with pytest.raises(ValueError, match="No top module found"):
        yosys_json.getTopModule()


def test_getNetPortSrcSinks(mocker: MockerFixture, tmp_path: Path) -> None:
    """Test getNetPortSrcSinks method."""
    dff = {
        "hide_name": "",
        "attributes": {},
        "parameters": {},
        "type": "DFF",
        "port_directions": {"A": "input", "Y": "output"},
    }
    cells = {
        "A": dff | {"connections": {"A": [1], "Y": [2]}},
        "B": dff | {"connections": {"A": [2], "Y": [3]}},
    }
    yosys_json = _load(mocker, tmp_path, {"module1": _module({}, cells)})

    assert yosys_json.getNetPortSrcSinks(2) == (("A", "Y"), [("B", "A")])
