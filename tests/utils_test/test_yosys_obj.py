"""Test module for YosysJson class and related components using pytest.

This module provides comprehensive tests for the Yosys JSON parser, including parsing of
different HDL formats and netlist analysis methods.
"""

from pathlib import Path

import pytest
import pytest_mock

from fabulous.custom_exception import InvalidFileType, InvalidState
from fabulous.fabric_definition.yosys_obj import YosysJson


def _cell(cell_type: str, port_directions: dict, connections: dict) -> dict:
    """Build a Yosys-JSON cell entry for the parser fixtures."""
    return {
        "hide_name": 0,
        "type": cell_type,
        "parameters": {},
        "attributes": {},
        "port_directions": port_directions,
        "connections": connections,
    }


def _module(ports: dict, cells: dict) -> dict:
    """Build a Yosys-JSON module entry for the parser fixtures."""
    return {
        "attributes": {},
        "parameter_default_values": {},
        "ports": ports,
        "cells": cells,
        "memories": {},
        "netnames": {},
    }


def _port(direction: str, bits: list[int]) -> dict:
    """Build a Yosys-JSON port entry for the parser fixtures."""
    return {"direction": direction, "bits": bits}


def setup_mocks(
    monkeypatch: pytest.MonkeyPatch, json_data: dict, tmp_path: Path
) -> None:
    """Set up mocks."""
    monkeypatch.setattr(
        "subprocess.run",
        lambda *args, **kwargs: type(  # noqa: ARG005
            "MockResult",
            (),
            {"stdout": "mock output", "stderr": "", "returncode": 0},
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

    # Ensure FABulousSettings validation passes by providing a models pack.
    # Use tmp_path (pytest-isolated per-test dir) to avoid collisions between
    # concurrent test workers or users sharing the same machine.
    tmp_mp = tmp_path / "models_pack.v"
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


def test_yosys_json_file_not_exists(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """Test YosysJson with unsupported file type."""
    setup_mocks(monkeypatch, {}, tmp_path)
    fakePath = tmp_path / "file.txt"
    with pytest.raises(FileNotFoundError, match="does not exist"):
        YosysJson(fakePath)


def test_yosys_json_unsupported_file_type(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """Test YosysJson with unsupported file type."""
    setup_mocks(monkeypatch, {}, tmp_path)
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

    setup_mocks(monkeypatch, json_data, tmp_path)
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

    setup_mocks(monkeypatch, json_data, tmp_path)
    fakePath = tmp_path / "test_file.v"
    fakePath.touch()
    fakePath.with_suffix(".json").touch()
    yosys_json = YosysJson(fakePath)
    with pytest.raises(ValueError, match="No top module found"):
        _ = yosys_json.getTopModule()


def test_get_top_module_blackbox_fallback(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """Test getTopModule falls back to blackbox module when no top module exists."""
    json_data = {
        "creator": "Yosys 0.33",
        "modules": {
            "blackbox_mod": {
                "attributes": {"blackbox": 1},
                "parameter_default_values": {},
                "ports": {},
                "cells": {},
                "memories": {},
                "netnames": {},
            }
        },
        "models": {},
    }

    setup_mocks(monkeypatch, json_data, tmp_path)
    fakePath = tmp_path / "test_file.v"
    fakePath.touch()
    fakePath.with_suffix(".json").touch()
    yosys_json = YosysJson(fakePath)
    module_name, module = yosys_json.getTopModule()

    assert module_name == "blackbox_mod"
    assert "blackbox" in module.attributes


def test_get_top_module_prefers_top_over_blackbox(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """Test getTopModule prefers a top module over a blackbox module."""
    json_data = {
        "creator": "Yosys 0.33",
        "modules": {
            "blackbox_mod": {
                "attributes": {"blackbox": 1},
                "parameter_default_values": {},
                "ports": {},
                "cells": {},
                "memories": {},
                "netnames": {},
            },
            "top_mod": {
                "attributes": {"top": 1},
                "parameter_default_values": {},
                "ports": {},
                "cells": {},
                "memories": {},
                "netnames": {},
            },
        },
        "models": {},
    }

    setup_mocks(monkeypatch, json_data, tmp_path)
    fakePath = tmp_path / "test_file.v"
    fakePath.touch()
    fakePath.with_suffix(".json").touch()
    yosys_json = YosysJson(fakePath)
    module_name, module = yosys_json.getTopModule()

    assert module_name == "top_mod"
    assert "top" in module.attributes


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

    setup_mocks(monkeypatch, json_data, tmp_path)
    fakePath = tmp_path / "test_file.v"
    fakePath.touch()
    fakePath.with_suffix(".json").touch()
    yosys_json = YosysJson(fakePath)

    assert yosys_json.getNetPortSrcSinks(2) == (("A", "Y"), [("B", "A")])


def test_comb_arcs_breaks_registers(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """comb_arcs drops the sequential D->Q path through a register.

    A 2:1 mux (combinational) drives O from input vector I; a DFF samples the mux
    output into Q. Only the combinational I->O arc survives.
    """
    json_data = {
        "creator": "Yosys",
        "modules": {
            "test": _module(
                ports={
                    "I": _port("input", [2, 3]),
                    "O": _port("output", [4]),
                    "Q": _port("output", [5]),
                },
                cells={
                    "mux": _cell(
                        "$mux",
                        {"A": "input", "B": "input", "S": "input", "Y": "output"},
                        {"A": [2], "B": [3], "S": [10], "Y": [4]},
                    ),
                    "reg": _cell(
                        "$dff",
                        {"CLK": "input", "D": "input", "Q": "output"},
                        {"CLK": [9], "D": [4], "Q": [5]},
                    ),
                },
            )
        },
        "models": {},
    }
    setup_mocks(monkeypatch, json_data, tmp_path)
    src = tmp_path / "test.v"
    src.touch()
    src.with_suffix(".json").touch()
    yosys_json = YosysJson(src)

    assert yosys_json.comb_arcs("test") == {("I0", "O"), ("I1", "O")}


def test_comb_arcs_resolves_sequential_submodule(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """comb_arcs treats a submodule that holds a latch as sequential.

    A custom primitive `config_latch` is sequential (its own definition holds a
    latch) and feeds a combinational `cus_mux21` whose select comes from input S.
    The latch breaks the data path from D, so only S -> X is combinational.
    """
    json_data = {
        "creator": "Yosys",
        "modules": {
            "config_latch": _module({}, {"l": _cell("$dlatch", {}, {})}),
            "cus_mux21": _module({}, {"m": _cell("$mux", {}, {})}),
            "test": _module(
                ports={
                    "D": _port("input", [2]),
                    "S": _port("input", [3]),
                    "X": _port("output", [5]),
                },
                cells={
                    "latch": _cell(
                        "config_latch",
                        {"D": "input", "Q": "output"},
                        {"D": [2], "Q": [4]},
                    ),
                    "mux": _cell(
                        "cus_mux21",
                        {"A0": "input", "A1": "input", "S": "input", "X": "output"},
                        {"A0": [4], "A1": [4], "S": [3], "X": [5]},
                    ),
                },
            ),
        },
        "models": {},
    }
    setup_mocks(monkeypatch, json_data, tmp_path)
    src = tmp_path / "test.v"
    src.touch()
    src.with_suffix(".json").touch()
    yosys_json = YosysJson(src)

    assert yosys_json.comb_arcs("test") == {("S", "X")}


def test_comb_arcs_resolves_nested_sequential_submodule(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """comb_arcs finds a register nested two submodules deep.

    `config_latch` holds no register directly; it instantiates `latch_impl`,
    which holds the `$dlatch`. A one-level check would miss this and wrongly emit
    a D -> X arc through the latch, so only S -> X must survive.
    """
    json_data = {
        "creator": "Yosys",
        "modules": {
            "latch_impl": _module({}, {"l": _cell("$dlatch", {}, {})}),
            "config_latch": _module({}, {"impl": _cell("latch_impl", {}, {})}),
            "cus_mux21": _module({}, {"m": _cell("$mux", {}, {})}),
            "test": _module(
                ports={
                    "D": _port("input", [2]),
                    "S": _port("input", [3]),
                    "X": _port("output", [5]),
                },
                cells={
                    "latch": _cell(
                        "config_latch",
                        {"D": "input", "Q": "output"},
                        {"D": [2], "Q": [4]},
                    ),
                    "mux": _cell(
                        "cus_mux21",
                        {"A0": "input", "A1": "input", "S": "input", "X": "output"},
                        {"A0": [4], "A1": [4], "S": [3], "X": [5]},
                    ),
                },
            ),
        },
        "models": {},
    }
    setup_mocks(monkeypatch, json_data, tmp_path)
    src = tmp_path / "test.v"
    src.touch()
    src.with_suffix(".json").touch()
    yosys_json = YosysJson(src)

    assert yosys_json.comb_arcs("test") == {("S", "X")}


def test_comb_arcs_missing_module_raises(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """comb_arcs raises InvalidState when the module is absent from the netlist."""
    json_data = {"creator": "Yosys", "modules": {}, "models": {}}
    setup_mocks(monkeypatch, json_data, tmp_path)
    src = tmp_path / "test.v"
    src.touch()
    src.with_suffix(".json").touch()
    yosys_json = YosysJson(src)

    with pytest.raises(InvalidState, match="not found in the parsed netlist"):
        yosys_json.comb_arcs("nope")
