"""Tests for the standard-cell timing specifications.

Covers the `CellSpec` / `StdCellLibrary` pydantic models and the loader that
reads a PDK's library (liberty + techmap files and cells) from one section of
the project's `Fabric/std_cell_library.yaml`, including ${VAR} / relative path
resolution and the shipped JSON schema.
"""

import json
from pathlib import Path

import pytest
import yaml

import fabulous
from fabulous.fabric_definition.cell_spec import (
    CellFunction,
    CellSpec,
    StdCellLibrary,
    StdCellLibraryFile,
)


def _write_std_cell_library(project_dir: Path, body: str) -> None:
    """Write ``Fabric/std_cell_library.yaml`` under ``project_dir``."""
    fabric_dir = project_dir / "Fabric"
    fabric_dir.mkdir(parents=True, exist_ok=True)
    (fabric_dir / "std_cell_library.yaml").write_text(body)


def _template_fabric_dir() -> Path:
    """Return the shipped project-template ``Fabric`` directory."""
    return (
        Path(fabulous.__file__).parent
        / "fabric_files"
        / "FABulous_project_template_common"
        / "Fabric"
    )


def _repo_schema_path() -> Path:
    """Return the repo-level standard-cell library JSON schema path."""
    return (
        Path(fabulous.__file__).parent.parent
        / "schema"
        / "std_cell_library.schema.json"
    )


_SKY130_SECTION = """\
pdk::sky130A:
  liberty_files:
    - /pdk/sky130A/typ.lib
  techmap_files:
    - /pdk/sky130A/latch_map.v
  cells:
    buffer:
      - cell: sky130_fd_sc_hd__buf_1
        input_ports: [A]
        output_ports: [X]
      - cell: sky130_fd_sc_hd__buf_2
        input_ports: [A]
        output_ports: [X]
    tie_high:
      - cell: sky130_fd_sc_hd__conb_1
        output_ports: [HI]
"""


# --------------------------------- CellSpec ---------------------------------


def test_cell_spec_yosys_arg_buffer() -> None:
    spec = CellSpec(cell="buf_1", input_ports=["A"], output_ports=["X"])

    assert spec.yosys_arg == "buf_1 A X"


def test_cell_spec_yosys_arg_tie_cell() -> None:
    spec = CellSpec(cell="conb_1", output_ports=["HI"])

    assert spec.yosys_arg == "conb_1 HI"


def test_cell_spec_yosys_arg_multiple_ports() -> None:
    spec = CellSpec(cell="mux", input_ports=["S", "A", "B"], output_ports=["Y"])

    assert spec.yosys_arg == "mux S A B Y"


# ------------------------------ StdCellLibrary ------------------------------


def test_get_returns_all_cells_for_function() -> None:
    library = StdCellLibrary.model_validate(
        {
            "cells": {
                "buffer": [
                    {"cell": "buf_1", "input_ports": ["A"], "output_ports": ["X"]},
                    {"cell": "buf_2", "input_ports": ["A"], "output_ports": ["X"]},
                ]
            }
        }
    )

    buffers = library.get(CellFunction.BUFFER)

    assert [b.cell for b in buffers] == ["buf_1", "buf_2"]


def test_get_missing_function_returns_empty() -> None:
    library = StdCellLibrary.model_validate(
        {"cells": {"buffer": [{"cell": "buf_1", "output_ports": ["X"]}]}}
    )

    assert library.get(CellFunction.TIE_LOW) == []


def test_defaults_are_empty() -> None:
    library = StdCellLibrary()

    assert library.liberty_files == []
    assert library.techmap_files == []
    assert library.get(CellFunction.BUFFER) == []


def test_load_returns_library(tmp_path: Path) -> None:
    _write_std_cell_library(tmp_path, _SKY130_SECTION)

    library = StdCellLibrary.load(tmp_path, "sky130A")

    assert library.liberty_files == [Path("/pdk/sky130A/typ.lib")]
    assert library.techmap_files == [Path("/pdk/sky130A/latch_map.v")]
    assert [b.cell for b in library.get(CellFunction.BUFFER)] == [
        "sky130_fd_sc_hd__buf_1",
        "sky130_fd_sc_hd__buf_2",
    ]
    tie_high = library.get(CellFunction.TIE_HIGH)[0]
    assert tie_high.yosys_arg == "sky130_fd_sc_hd__conb_1 HI"


def test_load_missing_file_raises(tmp_path: Path) -> None:
    with pytest.raises(FileNotFoundError, match="Standard-cell library file not found"):
        StdCellLibrary.load(tmp_path, "sky130A")


def test_load_missing_section_raises(tmp_path: Path) -> None:
    _write_std_cell_library(tmp_path, _SKY130_SECTION)

    with pytest.raises(ValueError, match="No 'pdk::ihp-sg13g2' section"):
        StdCellLibrary.load(tmp_path, "ihp-sg13g2")


def test_load_unknown_cell_function_raises(tmp_path: Path) -> None:
    _write_std_cell_library(
        tmp_path,
        "pdk::sky130A:\n  cells:\n    not_a_function:\n      - cell: x\n",
    )

    with pytest.raises(ValueError, match="StdCellLibrary"):
        StdCellLibrary.load(tmp_path, "sky130A")


# --------------------------- path resolution -------------------------------


def _buffer_section(liberty: str) -> str:
    """A minimal section with one buffer and the given liberty list entry."""
    return (
        "pdk::p:\n"
        f"  liberty_files:\n    - {liberty}\n"
        "  cells:\n"
        "    buffer:\n"
        "      - {cell: b, input_ports: [A], output_ports: [X]}\n"
    )


def test_expands_variables(tmp_path: Path) -> None:
    _write_std_cell_library(tmp_path, _buffer_section("${PDK_ROOT}/${PDK}/x.lib"))

    library = StdCellLibrary.load(tmp_path, "p", {"PDK_ROOT": "/pdks", "PDK": "p"})

    assert library.liberty_files == [Path("/pdks/p/x.lib")]


def test_absolute_path_unchanged(tmp_path: Path) -> None:
    _write_std_cell_library(tmp_path, _buffer_section("/abs/x.lib"))

    library = StdCellLibrary.load(tmp_path, "p", {"PDK_ROOT": "/pdks"})

    assert library.liberty_files == [Path("/abs/x.lib")]


def test_relative_path_resolved_against_project_dir(tmp_path: Path) -> None:
    _write_std_cell_library(tmp_path, _buffer_section("cells/x.lib"))

    library = StdCellLibrary.load(tmp_path, "p")

    assert library.liberty_files == [tmp_path / "cells" / "x.lib"]


def test_unknown_variable_raises(tmp_path: Path) -> None:
    _write_std_cell_library(tmp_path, _buffer_section("${NOPE}/x.lib"))

    with pytest.raises(ValueError, match="Unknown variable"):
        StdCellLibrary.load(tmp_path, "p", {"PDK_ROOT": "/pdks"})


# ------------------------------ shipped schema -----------------------------


def test_shipped_schema_matches_model() -> None:
    shipped = json.loads(_repo_schema_path().read_text())

    # If this fails after a model or pydantic change, regenerate
    # schema/std_cell_library.schema.json from StdCellLibraryFile.model_json_schema.
    assert shipped == StdCellLibraryFile.model_json_schema()


def test_template_sections_load() -> None:
    project_dir = _template_fabric_dir().parent
    sections = yaml.safe_load(
        (_template_fabric_dir() / "std_cell_library.yaml").read_text()
    )

    for section in sections:
        pdk = section.removeprefix("pdk::")
        library = StdCellLibrary.load(
            project_dir, pdk, {"PDK_ROOT": "/pdks", "PDK": pdk}
        )
        assert library.liberty_files
        assert library.get(CellFunction.BUFFER)
