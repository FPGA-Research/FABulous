"""Tests for parsing tile port lines from CSV fabric definitions."""

from pathlib import Path

import pytest

from fabulous.custom_exception import InvalidFabricParameter, InvalidPortType
from fabulous.fabric_definition.define import IO, ConfigBitMode, Direction, Side
from fabulous.fabric_generator.parser.parse_csv import (
    parse_port_line,
    parse_tile_from_dir,
    parseFabricCSV,
    parseSupertilesCSV,
)
from fabulous.fabulous_settings import init_context

# (kind, physical side of the OUTPUT/start port, physical side of the INPUT/end port)
DIRECTIONAL_CASES = [
    ("NORTH", Side.NORTH, Side.SOUTH),
    ("SOUTH", Side.SOUTH, Side.NORTH),
    ("EAST", Side.EAST, Side.WEST),
    ("WEST", Side.WEST, Side.EAST),
]


class TestDirectionalPorts:
    """NORTH/SOUTH/EAST/WEST lines produce an OUTPUT/INPUT port pair."""

    @pytest.mark.parametrize(("kind", "startSide", "endSide"), DIRECTIONAL_CASES)
    def test_two_ports_with_expected_io_and_sides(
        self, kind: str, startSide: Side, endSide: Side
    ) -> None:
        ports, commonWirePair = parse_port_line(f"{kind},N1BEG,0,-1,N1END,4")

        assert len(ports) == 2
        output, input_ = ports

        assert output.io_direction is IO.OUTPUT
        assert output.name == "N1BEG"
        assert output.side_of_tile is startSide

        assert input_.io_direction is IO.INPUT
        assert input_.name == "N1END"
        assert input_.side_of_tile is endSide

        assert commonWirePair == ("N1BEG", "N1END")

    @pytest.mark.parametrize("kind", [c[0] for c in DIRECTIONAL_CASES])
    def test_shared_attributes_carry_through(self, kind: str) -> None:
        ports, _ = parse_port_line(f"{kind},N2BEG,0,-2,N2END,8")

        for port in ports:
            assert port.wire_direction is Direction[kind]
            assert port.source_name == "N2BEG"
            assert port.destination_name == "N2END"
            assert port.x_offset == 0
            assert port.y_offset == -2
            assert port.wire_count == 8

    def test_null_destination_keeps_name_and_pairs(self) -> None:
        ports, commonWirePair = parse_port_line("SOUTH,S4BEG,0,4,NULL,4")

        assert ports[1].name == "NULL"
        assert commonWirePair == ("S4BEG", "NULL")


class TestJumpPorts:
    """JUMP lines stay within a tile, so both ports sit on Side.ANY."""

    def test_two_ports_on_any_side(self) -> None:
        ports, _ = parse_port_line("JUMP,J_SR_BEG,0,0,J_SR_END,1")

        assert len(ports) == 2
        output, input_ = ports

        assert output.io_direction is IO.OUTPUT
        assert output.name == "J_SR_BEG"
        assert input_.io_direction is IO.INPUT
        assert input_.name == "J_SR_END"

        assert all(p.wire_direction is Direction.JUMP for p in ports)
        assert all(p.side_of_tile is Side.ANY for p in ports)

    def test_no_common_wire_pair(self) -> None:
        _, commonWirePair = parse_port_line("JUMP,J_SR_BEG,0,0,J_SR_END,1")

        assert commonWirePair is None


class TestUnknownPortType:
    """Lines that are not a known wire direction are rejected."""

    @pytest.mark.parametrize("kind", ["BEL", "MATRIX", "north", "FOO"])
    def test_raises_invalid_port_type(self, kind: str) -> None:
        with pytest.raises(InvalidPortType, match="Unknown port type"):
            parse_port_line(f"{kind},SRC_BEG,0,0,DST_END,1")


class TestPortNameTrailingDigit:
    """A declared port name must not end in a digit.

    Trailing digits are reserved for the index that wire expansion appends
    (``N1BEG`` -> `N1BEG0`, `N1BEG1` ...). A declared name that already
    ends in a digit (e.g. ``X0_Y4_2_X0_Y3``) becomes ambiguous once the index
    is appended, because downstream the trailing digits are read back as a bit
    index. Reject such names at the parsing boundary.
    """

    @pytest.mark.parametrize("kind", ["NORTH", "SOUTH", "EAST", "WEST", "JUMP"])
    def test_source_name_ending_in_digit_raises(self, kind: str) -> None:
        line = f"{kind},X0_Y4_2_X0_Y3,0,0,DST_END,1"
        with pytest.raises(InvalidPortType, match="digit"):
            parse_port_line(line)

    @pytest.mark.parametrize("kind", ["NORTH", "SOUTH", "EAST", "WEST", "JUMP"])
    def test_destination_name_ending_in_digit_raises(self, kind: str) -> None:
        line = f"{kind},SRC_BEG,0,0,X0_Y4_2_X0_Y3,1"
        with pytest.raises(InvalidPortType, match="digit"):
            parse_port_line(line)

    def test_single_trailing_digit_raises(self) -> None:
        with pytest.raises(InvalidPortType, match="digit"):
            parse_port_line("JUMP,BUS3,0,0,J_END,1")

    @pytest.mark.parametrize(
        "line",
        [
            "JUMP,J_SR_BEG,0,0,J_SR_END,1",
            "NORTH,N1BEG,0,-1,N1END,4",
            "SOUTH,S4BEG,0,4,NULL,4",
            "NORTH,NULL,0,-1,N1END,4",
        ],
    )
    def test_valid_names_do_not_raise(self, line: str) -> None:
        ports, _ = parse_port_line(line)
        assert ports


class TestUserCLKDirection:
    """`UserCLKDirection` in the Parameters block sets `Fabric.userCLKSide`."""

    @staticmethod
    def _set_direction(project: Path, value: str) -> Path:
        csv = project / "fabric.csv"
        csv.write_text(
            csv.read_text().replace(
                "ParametersBegin,", f"ParametersBegin,\nUserCLKDirection,{value},", 1
            )
        )
        return csv

    @pytest.mark.parametrize(
        ("value", "side"),
        [
            ("S2N", Side.SOUTH),
            ("N2S", Side.NORTH),
            ("W2E", Side.WEST),
            ("E2W", Side.EAST),
        ],
    )
    def test_direction_maps_to_entry_side(
        self, project: Path, value: str, side: Side
    ) -> None:
        init_context(project)
        fabric = parseFabricCSV(str(self._set_direction(project, value)))
        assert fabric.userCLKSide is side

    def test_default_is_south(self, project: Path) -> None:
        init_context(project)
        assert parseFabricCSV(str(project / "fabric.csv")).userCLKSide is Side.SOUTH

    def test_invalid_direction_raises(self, project: Path) -> None:
        init_context(project)
        with pytest.raises(InvalidFabricParameter, match="UP"):
            parseFabricCSV(str(self._set_direction(project, "UP")))


class TestConfigMemLocation:
    """Where a parsed tile expects its `ConfigMem.csv` to be."""

    @pytest.mark.parametrize(
        ("row", "expected"),
        [
            pytest.param(None, "LUT4AB_ConfigMem.csv", id="derived"),
            pytest.param(
                "CONFIGMEM,./elsewhere/Mapping.csv",
                "elsewhere/Mapping.csv",
                id="declared",
            ),
        ],
    )
    def test_the_tile_names_its_mapping_file(
        self, project: Path, row: str | None, expected: str
    ) -> None:
        """A CONFIGMEM line wins; without one the mapping sits beside the tile."""
        tile_csv = project / "Tile/LUT4AB/LUT4AB.csv"
        text = tile_csv.read_text()
        if row is None:
            text = "\n".join(
                line for line in text.splitlines() if not line.startswith("CONFIGMEM,")
            )
        else:
            text = "\n".join(
                row if line.startswith("CONFIGMEM,") else line
                for line in text.splitlines()
            )
        tile_csv.write_text(text + "\n")

        init_context(project)
        fabric = parseFabricCSV(str(project / "fabric.csv"))

        source = fabric.tileDic["LUT4AB"].config_mem.source
        assert source is not None
        assert source == (project / "Tile/LUT4AB" / expected).absolute()


@pytest.mark.parametrize(
    ("mode", "maps_bits"),
    [("frame_based", True), ("FlipFlopChain", False)],
    ids=["frame_based", "flip_flop_chain"],
)
def test_only_a_frame_based_fabric_maps_its_configuration_bits(
    project: Path, mode: str, maps_bits: bool
) -> None:
    """A chain fabric's tiles keep an empty memory."""
    fabric_csv = project / "fabric.csv"
    fabric_csv.write_text(
        fabric_csv.read_text().replace(
            "ConfigBitMode,frame_based,", f"ConfigBitMode,{mode},", 1
        )
    )

    init_context(project)
    fabric = parseFabricCSV(str(fabric_csv))

    assert (fabric.tileDic["LUT4AB"].config_mem.config_bits > 0) is maps_bits


def test_a_supertile_declared_in_the_fabric_csv_maps_into_its_own_directory(
    project: Path,
) -> None:
    """A supertile declared in `fabric.csv` expects its mapping beside its children."""
    init_context(project)
    fabric_csv = project / "fabric.csv"
    fabric = parseFabricCSV(str(fabric_csv))
    fabric_csv.write_text(
        fabric_csv.read_text()
        + "\nSuperTILE,DSP_INLINE,\nDSP_top,\nDSP_bot,\nEndSuperTILE,\n"
    )

    (super_tile,) = parseSupertilesCSV(fabric_csv, fabric.tileDic)

    assert super_tile.config_mem.source.parent == project / "Tile" / "DSP"


def test_a_chain_tile_parsed_from_its_directory_ignores_a_stale_mapping(
    project: Path,
) -> None:
    """A chain tile flow ignores a mapping left by a frame-based run."""
    tile_dir = project / "Tile" / "LUT4AB"
    (tile_dir / "LUT4AB_ConfigMem.csv").write_text("this is not a mapping\n")

    init_context(project)
    tile = parse_tile_from_dir(
        tile_dir,
        "LUT4AB",
        False,
        config_bit_mode=ConfigBitMode.FLIPFLOP_CHAIN,
        frame_bits_per_row=32,
        max_frames_per_col=20,
    )

    assert tile.config_mem.config_bits == 0
