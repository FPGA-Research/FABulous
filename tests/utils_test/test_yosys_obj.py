"""Test module for YosysJson class and related components using pytest.

This module provides comprehensive tests for the Yosys JSON parser, including parsing of
different HDL formats and netlist analysis methods.

Only `subprocess.run` is mocked: the netlist Yosys would emit is written to the
companion `.json` file, so `YosysJson` parses real JSON from disk.
"""

import json
from pathlib import Path

import pytest
import pytest_mock
from pytest_mock import MockerFixture, MockType

from fabulous.custom_exception import InvalidFileType
from fabulous.fabric_definition.yosys_obj import YosysJson


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


@pytest.mark.parametrize(
    (
        "suffix",
        "set_env",
        "json_text",
        "vhdl_text",
        "expected_calls",
        "expect_substrings",
    ),
    [
        (
            ".vhdl",
            {"FAB_PROJ_LANG": "VHDL"},
            '{"modules": {"test": {}}}',
            "entity test is end entity;",
            2,
            [(0, "ghdl"), (1, "yosys")],
        ),
        (
            ".sv",
            {},
            "{}",
            None,
            1,
            [(None, "read_verilog -sv")],
        ),
        (
            ".v",
            {},
            "{}",
            None,
            1,
            [(None, "read_verilog")],
        ),
    ],
)
def test_yosys_json_initialization_parametric(
    mocker: pytest_mock.MockerFixture,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    suffix: str,
    set_env: dict[str, str],
    json_text: str,
    vhdl_text: str | None,
    expected_calls: int,
    expect_substrings: list[tuple[int | None, str]],
) -> None:
    """Parametrized test for YosysJson initialization across HDL types."""
    # Mock external dependencies
    m = mocker.patch(
        "subprocess.run",
        return_value=type(
            "MockResult",
            (),
            {"stdout": "mock output", "stderr": "", "returncode": 0},
        )(),
    )

    # Apply environment if provided (e.g., force VHDL mode)
    for k, v in (set_env or {}).items():
        monkeypatch.setenv(k, v)

    # Provide a valid models pack path to satisfy FABulousSettings validation
    if suffix in {".vhd", ".vhdl"}:
        mp = tmp_path / "models_pack.vhdl"
    elif suffix == ".sv":
        mp = tmp_path / "models_pack.v"  # .v is acceptable for SystemVerilog projects
    else:
        mp = tmp_path / "models_pack.v"
    mp.write_text("// dummy models pack\n")
    monkeypatch.setenv("FAB_MODELS_PACK", str(mp))

    # Prepare files
    (tmp_path / "file.json").write_text(json_text)
    src = tmp_path / f"file{suffix}"
    if vhdl_text is not None:
        src.write_text(vhdl_text)
    else:
        src.touch()

    # Ensure companion json exists for .v as in original test
    src.with_suffix(".json").touch(exist_ok=True)

    # Run
    YosysJson(src)

    # Assertions
    assert m.call_count == expected_calls
    if expected_calls == 1:
        # Check any-call substrings against the single call args
        for _, needle in expect_substrings:
            assert needle in str(m.call_args)
    else:
        # Check indexed call substrings
        for idx, needle in expect_substrings:
            assert idx is not None
            assert needle in str(m.call_args_list[idx])


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
