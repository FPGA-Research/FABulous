"""Data models for the fast tile-local FABulous routing graph.

The fast graph stores tile-type routing resources as the source of truth and creates
concrete PIPs only when a caller asks for them.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from pathlib import Path

    from fabulous.fabric_definition.define import IO, Direction, Side


class RoutingPipKind(StrEnum):
    """Classify how a routing PIP is produced."""

    INTERNAL_MATRIX = "internal_matrix"
    EXTERNAL_WIRE = "external_wire"


@dataclass(frozen=True, slots=True)
class RoutingTilePortModel:
    """Serializable routing-port metadata from one tile CSV row.

    Attributes
    ----------
    direction : Direction
        FABulous routing direction.
    source_name : str
        CSV source name.
    x_offset : int
        CSV X offset.
    y_offset : int
        CSV Y offset.
    destination_name : str
        CSV destination name.
    wire_count : int
        Number of wires declared by the row.
    name : str
        Parsed FABulous port name.
    io : IO
        Port direction from the tile perspective.
    side : Side
        Physical side of tile.
    """

    direction: Direction
    source_name: str
    x_offset: int
    y_offset: int
    destination_name: str
    wire_count: int
    name: str
    io: IO
    side: Side


@dataclass(frozen=True, slots=True)
class RoutingTileBelModel:
    """Serializable BEL metadata needed for tile write-back.

    Attributes
    ----------
    source_path : Path
        BEL source file path.
    prefix : str
        BEL prefix used in tile CSV.
    name : str
        BEL source stem.
    module_name : str
        HDL module/entity name.
    inputs : tuple[str, ...]
        Internal BEL input wires.
    outputs : tuple[str, ...]
        Internal BEL output wires.
    external_inputs : tuple[str, ...]
        External BEL inputs.
    external_outputs : tuple[str, ...]
        External BEL outputs.
    config_bits : int
        BEL configuration bits.
    feature_names : tuple[str, ...]
        BEL feature names exposed to nextpnr.
    with_user_clk : bool
        Whether this BEL uses the user clock.
    """

    source_path: Path
    prefix: str
    name: str
    module_name: str
    inputs: tuple[str, ...]
    outputs: tuple[str, ...]
    external_inputs: tuple[str, ...]
    external_outputs: tuple[str, ...]
    config_bits: int
    feature_names: tuple[str, ...]
    with_user_clk: bool


@dataclass(frozen=True, slots=True)
class RoutingTileGenIOModel:
    """Serializable ``GEN_IO`` metadata needed for tile write-back.

    Attributes
    ----------
    prefix : str
        Generated IO prefix.
    pins : int
        Number of pins.
    io : IO
        Generated IO direction.
    config_bits : int
        Configuration-bit count.
    config_access : bool
        Whether this GEN_IO is a config-access port.
    inverted : bool
        Whether generated IO is inverted.
    clocked : bool
        Whether generated IO is clocked.
    clocked_comb : bool
        Whether clocked and combinational outputs are exposed.
    clocked_mux : bool
        Whether a clocked mux is generated.
    """

    prefix: str
    pins: int
    io: IO
    config_bits: int
    config_access: bool
    inverted: bool
    clocked: bool
    clocked_comb: bool
    clocked_mux: bool


@dataclass(frozen=True, slots=True)
class RoutingTileModel:
    """Tile-type metadata preserved for standalone source write-back.

    Attributes
    ----------
    tile_type : str
        FABulous tile type.
    tile_csv_path : Path
        Original tile CSV path.
    tile_dir : Path
        Directory containing the tile CSV.
    matrix_path : Path
        Matrix file referenced by the tile CSV.
    matrix_config_bits : int
        Parsed matrix configuration-bit count.
    with_user_clk : bool
        Whether any BEL in the tile uses the user clock.
    ports : tuple[RoutingTilePortModel, ...]
        Parsed routing port rows.
    bels : tuple[RoutingTileBelModel, ...]
        Parsed BEL rows.
    gen_ios : tuple[RoutingTileGenIOModel, ...]
        Parsed GEN_IO rows.
    """

    tile_type: str
    tile_csv_path: Path
    tile_dir: Path
    matrix_path: Path
    matrix_config_bits: int
    with_user_clk: bool
    ports: tuple[RoutingTilePortModel, ...]
    bels: tuple[RoutingTileBelModel, ...]
    gen_ios: tuple[RoutingTileGenIOModel, ...]


@dataclass(frozen=True, slots=True)
class RoutingEndpoint:
    """One nextpnr routing endpoint.

    Attributes
    ----------
    tile_x : int
        X coordinate.
    tile_y : int
        Y coordinate.
    wire : str
        Tile-local wire name.
    """

    tile_x: int
    tile_y: int
    wire: str

    @property
    def tile(self) -> tuple[int, int]:
        """Return endpoint coordinates.

        Returns
        -------
        tuple[int, int]
            ``(x, y)`` coordinates.
        """
        return (self.tile_x, self.tile_y)

    def render_tile(self) -> str:
        """Render this endpoint's tile for nextpnr.

        Returns
        -------
        str
            Tile coordinate text such as ``X1Y2``.
        """
        return f"X{self.tile_x}Y{self.tile_y}"


@dataclass(frozen=True, slots=True)
class RoutingResourceKey:
    """Tile-type-wide routing resource identity.

    Attributes
    ----------
    tile_type : str
        Owner tile type.
    kind : RoutingPipKind
        Resource kind.
    source_name : str
        Matrix source or CSV source name.
    destination_name : str
        Matrix destination or CSV destination name.
    direction : Direction | None
        External CSV direction.
    x_offset : int
        External CSV X offset.
    y_offset : int
        External CSV Y offset.
    wire_count : int | None
        External CSV wire count.
    wire_class : int | None
        External span class.
    matrix_path : Path | None
        Matrix path for internal matrix resources.
    wire_index : int | None
        Optional single-wire selector.
    """

    tile_type: str
    kind: RoutingPipKind
    source_name: str
    destination_name: str
    direction: Direction | None = None
    x_offset: int = 0
    y_offset: int = 0
    wire_count: int | None = None
    wire_class: int | None = None
    matrix_path: Path | None = None
    wire_index: int | None = None


@dataclass(frozen=True, slots=True)
class RoutingPip:
    """Concrete nextpnr PIP generated lazily from a tile resource.

    Attributes
    ----------
    pip_id : int | None
        Render-local PIP id.
    kind : RoutingPipKind
        PIP kind.
    source : RoutingEndpoint
        Source endpoint.
    destination : RoutingEndpoint
        Destination endpoint.
    delay : float
        PIP delay.
    name : str
        PIP display name.
    owner_tile : tuple[int, int]
        Tile that owns the resource.
    tile_type : str
        Owner tile type.
    resource_key : RoutingResourceKey
        Resource that generated the PIP.
    source_tile_type : str | None
        Source endpoint tile type if placed.
    destination_tile_type : str | None
        Destination endpoint tile type if placed.
    matrix_path : Path | None
        Matrix file for internal resources.
    emitted_x_offset : int
        Concrete X offset.
    emitted_y_offset : int
        Concrete Y offset.
    """

    pip_id: int | None
    kind: RoutingPipKind
    source: RoutingEndpoint
    destination: RoutingEndpoint
    delay: float
    name: str
    owner_tile: tuple[int, int]
    tile_type: str
    resource_key: RoutingResourceKey
    source_tile_type: str | None = None
    destination_tile_type: str | None = None
    matrix_path: Path | None = None
    emitted_x_offset: int = 0
    emitted_y_offset: int = 0

    def render(self) -> str:
        """Render as one nextpnr ``pips.txt`` line.

        Returns
        -------
        str
            Comma-separated PIP record.
        """
        delay = _format_pip_delay(self.delay)
        return (
            f"{self.source.render_tile()},{self.source.wire},"
            f"{self.destination.render_tile()},{self.destination.wire},"
            f"{delay},{self.name}"
        )

    @property
    def signature(self) -> tuple[str, str, str, str]:
        """Return the concrete endpoint identity.

        Returns
        -------
        tuple[str, str, str, str]
            Source tile/wire and destination tile/wire.
        """
        return (
            self.source.render_tile(),
            self.source.wire,
            self.destination.render_tile(),
            self.destination.wire,
        )


@dataclass(frozen=True, slots=True)
class RoutingGraphStats:
    """Summarized concrete routing graph counts.

    Attributes
    ----------
    total_pips : int
        Number of concrete PIPs materialized by active and inactive resources.
    active_pips : int
        Number of active concrete PIPs.
    disabled_pips : int
        Number of inactive concrete PIPs.
    internal_pips : int
        Number of active internal matrix PIPs.
    external_pips : int
        Number of active external PIPs.
    tile_types : int
        Number of tile types with active resources.
    resource_keys : int
        Number of active resource keys.
    """

    total_pips: int
    active_pips: int
    disabled_pips: int
    internal_pips: int
    external_pips: int
    tile_types: int
    resource_keys: int


@dataclass(frozen=True, slots=True)
class RoutingConfigBits:
    """Tile-local configuration-bit summary.

    Attributes
    ----------
    tile_type : str
        Tile type represented by this summary.
    matrix_config_bits : int
        Configuration bits required by active switch-matrix muxes.
    fixed_config_bits : int
        Configuration bits required by non-routing tile resources, currently BELs.
    total_config_bits : int
        Sum of matrix and fixed configuration bits.
    """

    tile_type: str
    matrix_config_bits: int
    fixed_config_bits: int
    total_config_bits: int


@dataclass(frozen=True, slots=True)
class RoutingResourceCounts:
    """Tile-local routing resource counts.

    Attributes
    ----------
    tile_type : str
        Tile type represented by this summary.
    external_active : int
        Active external CSV-style resources.
    external_disabled : int
        Disabled external CSV-style resources.
    matrix_active : int
        Active switch-matrix resources.
    matrix_disabled : int
        Disabled switch-matrix resources.
    total_active : int
        Total active routing resources.
    total_disabled : int
        Total disabled routing resources.
    total : int
        Total tracked routing resources.
    """

    tile_type: str
    external_active: int
    external_disabled: int
    matrix_active: int
    matrix_disabled: int
    total_active: int
    total_disabled: int
    total: int


def _format_pip_delay(delay: float) -> str:
    """Format a PIP delay like FABulous output.

    Parameters
    ----------
    delay : float
        Delay value.

    Returns
    -------
    str
        Formatted delay.
    """
    if isinstance(delay, float) and delay.is_integer():
        return str(int(delay))
    return str(delay)
