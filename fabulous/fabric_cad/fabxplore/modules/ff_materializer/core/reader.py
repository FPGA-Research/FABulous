"""Read pyosys designs and tile models for FF materialization."""

from __future__ import annotations

from typing import TYPE_CHECKING

from fabulous.fabric_cad.fabxplore.modules.ff_materializer.core.models import (
    FfMaterializerCell,
    FfMaterializerDesign,
    FfMaterializerTileModel,
)
from fabulous.fabric_cad.fabxplore.modules.ff_materializer.core.tile_compiler import (
    FfMaterializerTileCompiler,
)

if TYPE_CHECKING:
    from pathlib import Path

    from fabulous.fabric_cad.fabxplore.pyosys.pyosys_bridge import PyosysBridge
    from fabulous.fabric_definition.yosys_obj import YosysCellDetails


class FfMaterializerReader:
    """Extract cells and tile metadata needed by FF materialization."""

    def read_design(
        self,
        design: PyosysBridge,
        top_name: str,
    ) -> FfMaterializerDesign:
        """Read one top module from a pyosys bridge.

        Parameters
        ----------
        design : PyosysBridge
            Source design.
        top_name : str
            Top module to inspect.

        Returns
        -------
        FfMaterializerDesign
            Internal design view.

        Raises
        ------
        RuntimeError
            If ``top_name`` is not present.
        """
        design_object = design.to_py_object()
        if top_name not in design_object.modules:
            available = ", ".join(sorted(design_object.modules))
            raise RuntimeError(
                f"Top module '{top_name}' not found. Available: {available}"
            )

        module = design_object.modules[top_name]
        cells = tuple(
            self._parse_cell(cell_id, cell) for cell_id, cell in module.cells.items()
        )
        return FfMaterializerDesign(top_name=top_name, cells=cells)

    def read_tile_model(
        self,
        verilog_path: Path,
        top_name: str,
        inputs: list[str],
        outputs: list[str],
        configs: list[str] | None,
        config_prefixes: list[str] | None,
    ) -> FfMaterializerTileModel:
        """Read and normalize the replacement tile model.

        Parameters
        ----------
        verilog_path : Path
            Verilog source defining the tile.
        top_name : str
            Tile top module name.
        inputs : list[str]
            Scalar data/control input ports exposed to the materializer.
        outputs : list[str]
            Scalar output ports exposed to the materializer.
        configs : list[str] | None
            Explicit scalar config names.
        config_prefixes : list[str] | None
            Prefixes used to discover scalar config names from BLIF inputs.

        Returns
        -------
        FfMaterializerTileModel
            Tile model containing BLIF text and scalar config names.
        """
        blif_text = FfMaterializerTileCompiler().emit_blif_text(
            verilog_path=verilog_path,
            top_name=top_name,
        )
        discovered = _discover_config_bits(blif_text, tuple(config_prefixes or ()))
        config_bits = tuple(dict.fromkeys([*discovered, *(configs or [])]))
        return FfMaterializerTileModel(
            top_name=top_name,
            verilog_path=verilog_path,
            blif_text=blif_text,
            inputs=tuple(inputs),
            outputs=tuple(outputs),
            config_bits=config_bits,
            config_prefixes=tuple(config_prefixes or ()),
        )

    def _parse_cell(
        self,
        cell_id: str,
        cell: YosysCellDetails,
    ) -> FfMaterializerCell:
        """Parse one Yosys object-model cell.

        Parameters
        ----------
        cell_id : str
            Cell instance name.
        cell : YosysCellDetails
            Cell details from the object model.

        Returns
        -------
        FfMaterializerCell
            Internal cell view.
        """
        return FfMaterializerCell(
            cell_id=_clean_name(cell_id),
            cell_type=str(cell.type).lstrip("\\"),
            parameters={key: str(value) for key, value in cell.parameters.items()},
            connections={
                key: tuple(str(bit) for bit in bits)
                for key, bits in cell.connections.items()
            },
            port_directions={
                key: str(value) for key, value in cell.port_directions.items()
            },
        )


def _discover_config_bits(
    blif_text: str,
    config_prefixes: tuple[str, ...],
) -> tuple[str, ...]:
    """Discover scalar config inputs from BLIF text.

    Parameters
    ----------
    blif_text : str
        BLIF emitted from the tile model.
    config_prefixes : tuple[str, ...]
        Prefixes used to classify BLIF inputs as config bits.

    Returns
    -------
    tuple[str, ...]
        Discovered scalar config inputs in BLIF order.
    """
    if not config_prefixes:
        return ()
    found: list[str] = []
    for line in _logical_blif_lines(blif_text):
        parts = line.split()
        if not parts or parts[0] != ".inputs":
            continue
        for token in parts[1:]:
            clean = _clean_name(token)
            if any(
                clean == prefix or clean.startswith(f"{prefix}[")
                for prefix in config_prefixes
            ):
                found.append(clean)
    return tuple(dict.fromkeys(found))


def _logical_blif_lines(blif_text: str) -> list[str]:
    """Return BLIF lines with continuations joined.

    Parameters
    ----------
    blif_text : str
        Raw BLIF text.

    Returns
    -------
    list[str]
        Logical BLIF lines.
    """
    lines: list[str] = []
    current = ""
    for raw_line in blif_text.splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        if line.endswith("\\"):
            current += line[:-1].strip() + " "
            continue
        lines.append((current + line).strip())
        current = ""
    if current:
        lines.append(current.strip())
    return lines


def _clean_name(name: object) -> str:
    """Return a name without a leading Yosys escape backslash.

    Parameters
    ----------
    name : object
        Yosys name-like object.

    Returns
    -------
    str
        Clean name.
    """
    return str(name).removeprefix("\\")
