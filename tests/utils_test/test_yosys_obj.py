"""Test module for YosysJson class and related components using pytest.

This module provides comprehensive tests for the Yosys JSON parser, including parsing of
different HDL formats and netlist analysis methods.
"""

from pathlib import Path

import pytest
import pytest_mock

from fabulous.custom_exception import InvalidFileType, InvalidState
from fabulous.fabric_definition.yosys_obj import YosysJson, YosysNetDetails


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


def _module(ports: dict, cells: dict, attributes: dict | None = None) -> dict:
    """Build a Yosys-JSON module entry for the parser fixtures."""
    return {
        "attributes": {} if attributes is None else attributes,
        "parameter_default_values": {},
        "ports": ports,
        "cells": cells,
        "memories": {},
        "netnames": {},
    }


def _port(direction: str, bits: list[int]) -> dict:
    """Build a Yosys-JSON port entry for the parser fixtures."""
    return {"direction": direction, "bits": bits}


def _instantiate(cell_type: str, directions: dict[str, str]) -> dict:
    """Build a `test` module wrapping one `cell_type`, one net bit per port."""
    bits = {port: [index + 2] for index, port in enumerate(directions)}
    return _module(
        ports={port: _port(d, bits[port]) for port, d in directions.items()},
        cells={"u": _cell(cell_type, directions, bits)},
    )


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


def _parse(monkeypatch: pytest.MonkeyPatch, tmp_path: Path, modules: dict) -> YosysJson:
    """Parse `modules` as the Yosys JSON of a Verilog source."""
    setup_mocks(monkeypatch, {"creator": "Yosys", "modules": modules}, tmp_path)
    src = tmp_path / "test.v"
    src.touch()
    src.with_suffix(".json").touch()
    return YosysJson(src)


_MUX = _cell(
    "$_MUX_",
    {"A": "input", "B": "input", "S": "input", "Y": "output"},
    {"A": [2], "B": [3], "S": [10], "Y": [4]},
)


@pytest.mark.parametrize(
    "register",
    [
        pytest.param(
            _cell(
                "$_DFF_P_",
                {"C": "input", "D": "input", "Q": "output"},
                {"C": [9], "D": [4], "Q": [5]},
            ),
            id="dff",
        ),
        pytest.param(
            _cell(
                "$_DFFSR_PNN_",
                {"C": "input", "S": "input", "R": "input", "D": "input", "Q": "output"},
                {"C": [9], "S": [11], "R": [12], "D": [4], "Q": [5]},
            ),
            id="dffsr",
        ),
        pytest.param(
            _cell(
                "$_DLATCH_P_",
                {"E": "input", "D": "input", "Q": "output"},
                {"E": [9], "D": [4], "Q": [5]},
            ),
            id="latch",
        ),
    ],
)
def test_bit_graph_breaks_registers(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, register: dict
) -> None:
    """A register or latch adds no edge, while the mux beside it joins every input.

    The mux drives net 4 from nets 2, 3 and 10; `register` reads net 4 into net 5.
    """
    modules = {"test": _module(ports={}, cells={"mux": _MUX, "reg": register})}
    yosys_json = _parse(monkeypatch, tmp_path, modules)

    assert set(yosys_json.bit_graph("test").edges) == {(2, 4), (3, 4), (10, 4)}


_LATCH = _cell("$_DLATCH_P_", {"D": "input", "Q": "output"}, {"D": [2], "Q": [4]})
_BYPASS = _cell("$_NOT_", {"A": "input", "Y": "output"}, {"A": [3], "Y": [5]})
_BYPASS_PORTS = {
    "D": _port("input", [2]),
    "B": _port("input", [3]),
    "Q": _port("output", [4]),
    "X": _port("output", [5]),
}
_BYPASS_DIRECTIONS = {"D": "input", "B": "input", "Q": "output", "X": "output"}


@pytest.mark.parametrize(
    ("submodules", "cell_type", "directions", "expected"),
    [
        # The latch cuts D -> Q, but the bypass B -> X beside it is still an arc.
        pytest.param(
            {"reg_bypass": _module(_BYPASS_PORTS, {"l": _LATCH, "n": _BYPASS})},
            "reg_bypass",
            _BYPASS_DIRECTIONS,
            {(3, 5)},
            id="bypass",
        ),
        pytest.param(
            {
                "latch_impl": _module(
                    {"D": _port("input", [2]), "Q": _port("output", [4])},
                    {"l": _LATCH},
                ),
                "reg_bypass": _module(
                    _BYPASS_PORTS,
                    {
                        "l": _cell(
                            "latch_impl",
                            {"D": "input", "Q": "output"},
                            {"D": [2], "Q": [4]},
                        ),
                        "n": _BYPASS,
                    },
                ),
            },
            "reg_bypass",
            _BYPASS_DIRECTIONS,
            {(3, 5)},
            id="nested-bypass",
        ),
        # An assign-only module has no cells; its ports share one net bit.
        pytest.param(
            {
                "my_buf": _module(
                    {"A": _port("input", [2]), "X": _port("output", [2])}, {}
                )
            },
            "my_buf",
            {"A": "input", "X": "output"},
            {(2, 3)},
            id="passthrough",
        ),
        # A blackbox hides its arcs, so every input reaches every output.
        pytest.param(
            {
                "macro": _module(
                    {
                        "A": _port("input", [2]),
                        "B": _port("input", [3]),
                        "X": _port("output", [4]),
                        "Y": _port("output", [5]),
                    },
                    {},
                    attributes={"blackbox": 1},
                )
            },
            "macro",
            {"A": "input", "B": "input", "X": "output", "Y": "output"},
            {(2, 4), (2, 5), (3, 4), (3, 5)},
            id="blackbox",
        ),
    ],
)
def test_bit_graph_follows_submodule_arcs(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    submodules: dict,
    cell_type: str,
    directions: dict[str, str],
    expected: set[tuple[int, int]],
) -> None:
    """A submodule instance adds exactly the arcs it has between its ports."""
    modules = {**submodules, "test": _instantiate(cell_type, directions)}
    yosys_json = _parse(monkeypatch, tmp_path, modules)

    assert set(yosys_json.bit_graph("test").edges) == expected


def test_bit_graph_rejects_unknown_cell(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """bit_graph refuses to guess the arcs of a type with no module."""
    modules = {"test": _instantiate("prim", {"A": "input", "X": "output"})}
    yosys_json = _parse(monkeypatch, tmp_path, modules)

    with pytest.raises(InvalidState, match="no module in the netlist"):
        yosys_json.bit_graph("test")


@pytest.mark.parametrize(
    ("net", "expected"),
    [
        pytest.param({"bits": [2]}, ["n"], id="scalar"),
        pytest.param({"bits": [2, 3]}, ["n[0]", "n[1]"], id="downto"),
        pytest.param({"bits": [2, 3], "offset": 4}, ["n[4]", "n[5]"], id="offset"),
        pytest.param({"bits": [2, 3], "upto": 1}, ["n[1]", "n[0]"], id="upto"),
    ],
)
def test_net_bit_names(net: dict, expected: list[str]) -> None:
    """A net bit is named by its Verilog bit-select."""
    details = YosysNetDetails(hide_name=0, attributes={}, **net)

    assert details.bit_names("n") == expected
