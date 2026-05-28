"""Probe tests for fabric-object data and structured CSV write-back.

These tests are intentionally self-contained and do not implement the fabric-wide
optimizer itself. They create a tiny temporary FABulous project, inspect the parsed
``Fabric`` object, rewrite a source CSV row using structured columns, reload the
fabric, and regenerate nextpnr routing metadata. The goal is to document which data
is available from the parsed object and where write-back still needs source-file
knowledge.
"""

from __future__ import annotations

from dataclasses import fields
from typing import TYPE_CHECKING

from fabulous.fabric_cad.gen_npnr_model import genNextpnrModel
from fabulous.fabric_definition.define import IO, Direction, Side
from fabulous.fabric_definition.port import Port
from fabulous.fabric_generator.parser.parse_csv import parseFabricCSV

if TYPE_CHECKING:
    from pathlib import Path

    from fabulous.fabric_definition.fabric import Fabric


def test_fabric_object_exposes_structured_wire_data_and_metadata_rewrites(
    tmp_path: Path,
) -> None:
    """Inspect fabric data, rewrite a structural wire row, and refresh metadata."""
    project_dir = _write_minimal_project(tmp_path)
    fabric = parseFabricCSV(project_dir / "fabric.csv")

    tile_type = fabric.tileDic["Toy"]
    grid_tile = fabric.tile[0][0]
    long_output_ports = [
        port
        for port in tile_type.portsInfo
        if port.wireDirection is Direction.EAST
        and port.xOffset == 2
        and port.yOffset == 0
        and port.inOut is IO.OUTPUT
    ]

    assert len(long_output_ports) == 1
    assert long_output_ports[0].wireCount == 3
    assert long_output_ports[0].sideOfTile is Side.EAST
    assert _port_field_names() == {
        "wireDirection",
        "sourceName",
        "xOffset",
        "yOffset",
        "destinationName",
        "wireCount",
        "name",
        "inOut",
        "sideOfTile",
    }
    assert grid_tile is not None
    assert _external_pip_count(genNextpnrModel(fabric)[0]) > 0

    metadata_dir = _write_routing_metadata(project_dir, fabric)
    original_pips = (metadata_dir / "pips.txt").read_text(encoding="utf-8")

    changed_rows = _rewrite_wire_count_by_structure(
        csv_path=project_dir / "Tile" / "include" / "Base.csv",
        direction=Direction.EAST,
        x_offset=2,
        y_offset=0,
        old_wire_count=3,
        new_wire_count=1,
    )
    assert changed_rows == 1

    reloaded = parseFabricCSV(project_dir / "fabric.csv")
    reloaded_tile_type = reloaded.tileDic["Toy"]
    reloaded_long_output_ports = [
        port
        for port in reloaded_tile_type.portsInfo
        if port.wireDirection is Direction.EAST
        and port.xOffset == 2
        and port.yOffset == 0
        and port.inOut is IO.OUTPUT
    ]

    assert len(reloaded_long_output_ports) == 1
    assert reloaded_long_output_ports[0].wireCount == 1
    assert _wire_count(reloaded) < _wire_count(fabric)

    _write_routing_metadata(project_dir, reloaded)
    updated_pips = (metadata_dir / "pips.txt").read_text(encoding="utf-8")

    assert updated_pips != original_pips
    assert _external_pip_count(updated_pips) < _external_pip_count(original_pips)


def _write_minimal_project(project_dir: Path) -> Path:
    """Write a tiny FABulous project with one included wire-definition file.

    Parameters
    ----------
    project_dir : Path
        Temporary project directory.

    Returns
    -------
    Path
        Project directory containing ``fabric.csv``.
    """
    include_dir = project_dir / "Tile" / "include"
    tile_dir = project_dir / "Tile" / "Toy"
    include_dir.mkdir(parents=True)
    tile_dir.mkdir(parents=True)

    (project_dir / "fabric.csv").write_text(
        """\
FabricBegin
Toy,Toy
FabricEnd

ParametersBegin
ConfigBitMode,frame_based
GenerateDelayInSwitchMatrix,80
MultiplexerStyle,custom
SuperTileEnable,FALSE
Tile,./Tile/Toy/Toy.csv
ParametersEnd
""",
        encoding="utf-8",
    )
    (include_dir / "Base.csv").write_text(
        """\
#direction,source_name,X-offset,Y-offset,destination_name,wires
EAST,LONG_BEG,2,0,LONG_END,3
JUMP,LOCAL_BEG,0,0,LOCAL_END,1
""",
        encoding="utf-8",
    )
    (tile_dir / "Toy.csv").write_text(
        """\
TILE,Toy
INCLUDE,../include/Base.csv
MATRIX,./Toy_switch_matrix.list
EndTILE
""",
        encoding="utf-8",
    )
    (tile_dir / "Toy_switch_matrix.list").write_text(
        "LONG_END0,LOCAL_BEG0\n",
        encoding="utf-8",
    )
    return project_dir


def _port_field_names() -> set[str]:
    """Return fields preserved by the parsed ``Port`` object.

    Returns
    -------
    set[str]
        Port dataclass field names.
    """
    return {field.name for field in fields(Port)}


def _rewrite_wire_count_by_structure(
    csv_path: Path,
    direction: Direction,
    x_offset: int,
    y_offset: int,
    old_wire_count: int,
    new_wire_count: int,
) -> int:
    """Rewrite CSV rows selected by structured wire columns.

    Parameters
    ----------
    csv_path : Path
        CSV file to rewrite.
    direction : Direction
        Direction column to match.
    x_offset : int
        X-offset column to match.
    y_offset : int
        Y-offset column to match.
    old_wire_count : int
        Existing wire-count column to match.
    new_wire_count : int
        Replacement wire-count column value.

    Returns
    -------
    int
        Number of changed rows.

    Raises
    ------
    ValueError
        If ``new_wire_count`` is not positive.
    """
    if new_wire_count <= 0:
        raise ValueError("new_wire_count must be positive")

    changed = 0
    output_lines: list[str] = []
    for line in csv_path.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            output_lines.append(line)
            continue

        columns = line.split(",")
        if len(columns) >= 6 and _matches_wire_row(
            columns=columns,
            direction=direction,
            x_offset=x_offset,
            y_offset=y_offset,
            old_wire_count=old_wire_count,
        ):
            columns[5] = str(new_wire_count)
            changed += 1
        output_lines.append(",".join(columns))

    csv_path.write_text("\n".join(output_lines) + "\n", encoding="utf-8")
    return changed


def _matches_wire_row(
    columns: list[str],
    direction: Direction,
    x_offset: int,
    y_offset: int,
    old_wire_count: int,
) -> bool:
    """Return whether CSV columns match a structured wire selector.

    Parameters
    ----------
    columns : list[str]
        CSV row columns.
    direction : Direction
        Direction column to match.
    x_offset : int
        X-offset column to match.
    y_offset : int
        Y-offset column to match.
    old_wire_count : int
        Existing wire-count column to match.

    Returns
    -------
    bool
        Whether the row matches.
    """
    try:
        return (
            columns[0].strip() == direction.value
            and int(columns[2]) == x_offset
            and int(columns[3]) == y_offset
            and int(columns[5]) == old_wire_count
        )
    except ValueError:
        return False


def _write_routing_metadata(project_dir: Path, fabric: Fabric) -> Path:
    """Write nextpnr routing-model metadata for a parsed fabric.

    Parameters
    ----------
    project_dir : Path
        Project directory where ``.FABulous`` should be refreshed.
    fabric : Fabric
        Parsed FABulous fabric object.

    Returns
    -------
    Path
        Metadata directory.
    """
    metadata_dir = project_dir / ".FABulous"
    metadata_dir.mkdir(exist_ok=True)
    pips, bel, bel_v2, template_pcf = genNextpnrModel(fabric)
    (metadata_dir / "pips.txt").write_text(pips, encoding="utf-8")
    (metadata_dir / "bel.txt").write_text(bel, encoding="utf-8")
    (metadata_dir / "bel.v2.txt").write_text(bel_v2, encoding="utf-8")
    (metadata_dir / "template.pcf").write_text(template_pcf, encoding="utf-8")
    return metadata_dir


def _wire_count(fabric: Fabric) -> int:
    """Count expanded tile wires in a fabric grid.

    Parameters
    ----------
    fabric : Fabric
        Parsed FABulous fabric object.

    Returns
    -------
    int
        Total expanded ``Wire`` objects across placed tiles.
    """
    return sum(len(tile.wireList) for _xy, tile in fabric if tile is not None)


def _external_pip_count(pips_text: str) -> int:
    """Count nextpnr PIP lines in external routing sections.

    Parameters
    ----------
    pips_text : str
        Text produced by ``genNextpnrModel``.

    Returns
    -------
    int
        Number of non-comment external PIP lines.
    """
    in_external = False
    count = 0
    for line in pips_text.splitlines():
        if line.startswith("#Tile-internal"):
            in_external = False
        elif line.startswith("#Tile-external"):
            in_external = True
        elif in_external and line and not line.startswith("#"):
            count += 1
    return count
