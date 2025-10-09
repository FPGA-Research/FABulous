"""
Test module for YosysJson class and related components using pytest.

This module provides comprehensive tests for the Yosys JSON parser,
including parsing of different HDL formats and netlist analysis methods.
"""

import tempfile
from pathlib import Path

import pytest
import pytest_mock

from FABulous.custom_exception import InvalidFileType
from FABulous.fabric_definition.Yosys_obj import YosysJson


def setup_mocks(monkeypatch: pytest.MonkeyPatch, json_data: dict) -> None:
    """Set up mocks."""
    monkeypatch.setattr(
        "subprocess.run",
        lambda cmd, check=False, capture_output=False: type(  # noqa: ARG005
            "MockResult", (), {"stdout": b"mock output", "stderr": b""}
        )(),
    )
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

    # Ensure FABulousSettings validation passes by providing a models pack
    tmp_mp = Path(tempfile.gettempdir()) / "models_pack.v"
    try:
        tmp_mp.write_text("// test models pack\n")
    except OSError:
        # In rare cases temp dir may be read-only; fallback to current working dir
        tmp_mp = Path.cwd() / "models_pack.v"
        tmp_mp.write_text("// test models pack\n")
    monkeypatch.setenv("FAB_MODELS_PACK", str(tmp_mp))


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
            "MockResult", (), {"stdout": b"mock output", "stderr": b""}
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


def test_yosys_json_file_not_exists(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """Test YosysJson with unsupported file type."""
    setup_mocks(monkeypatch, {})
    fakePath = tmp_path / "file.txt"
    with pytest.raises(FileNotFoundError, match="does not exist"):
        YosysJson(fakePath)


def test_yosys_json_unsupported_file_type(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
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
    module_name, top_module = yosys_json.getTopModule()

    assert "top" in top_module.attributes
    assert top_module.attributes["top"] == 1
    assert module_name == "module1"


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
    """Test getNetPortSrcSinks method."""
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
