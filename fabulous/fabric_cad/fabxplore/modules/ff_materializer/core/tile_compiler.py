"""Compile FF materializer tile Verilog into SAT-ready BLIF."""

from __future__ import annotations

from pathlib import Path
from tempfile import TemporaryDirectory
from typing import TYPE_CHECKING

from fabulous.fabric_cad.fabxplore.pyosys.pyosys_bridge import PyosysBridge

if TYPE_CHECKING:
    from collections.abc import Mapping


class FfMaterializerTileCompiler:
    """Compile replacement tile RTL into a normalized BLIF model."""

    def emit_blif_text(
        self,
        verilog_path: Path,
        top_name: str,
        fixed_ports: Mapping[str, int | bool] | None = None,
    ) -> str:
        """Compile tile RTL and return BLIF text.

        Parameters
        ----------
        verilog_path : Path
            Verilog source defining the tile.
        top_name : str
            Tile top module name.
        fixed_ports : Mapping[str, int | bool] | None
            Optional scalar input ports to tie to constants before lowering.

        Returns
        -------
        str
            Emitted BLIF text.
        """
        with TemporaryDirectory(prefix="ff_materializer_tile_") as td:
            blif_path = Path(td) / "tile.blif"
            self.write_blif_path(
                verilog_path=verilog_path,
                top_name=top_name,
                blif_path=blif_path,
                fixed_ports=fixed_ports,
            )
            return blif_path.read_text(encoding="utf-8")

    def write_blif_path(
        self,
        verilog_path: Path,
        top_name: str,
        blif_path: Path,
        fixed_ports: Mapping[str, int | bool] | None = None,
    ) -> None:
        """Compile tile RTL and write BLIF to a path.

        Parameters
        ----------
        verilog_path : Path
            Verilog source defining the tile.
        top_name : str
            Tile top module name.
        blif_path : Path
            Destination BLIF path.
        fixed_ports : Mapping[str, int | bool] | None
            Optional scalar input ports to tie to constants before lowering.
        """
        bridge = PyosysBridge(debug=False)
        bridge.read_verilog_paths([verilog_path], replace_design=True)
        bridge.run_pass(f"prep -top {top_name}")
        self._apply_fixed_ports(bridge, top_name, fixed_ports or {})
        self._lower_tile(bridge, blif_path)

    def _apply_fixed_ports(
        self,
        bridge: PyosysBridge,
        top_name: str,
        fixed_ports: Mapping[str, int | bool],
    ) -> None:
        """Tie selected top-level tile ports to constants.

        Parameters
        ----------
        bridge : PyosysBridge
            Yosys bridge holding the tile design.
        top_name : str
            Tile top module name.
        fixed_ports : Mapping[str, int | bool]
            Scalar input ports to tie to constants.
        """
        if not fixed_ports:
            return
        bridge.run_pass(f"cd {top_name}")
        for port, value in sorted(fixed_ports.items()):
            bridge.run_pass(f"connect -set {port} 1'{_bool_bit(value)}")
        bridge.run_pass("cd ..")

    def _lower_tile(self, bridge: PyosysBridge, blif_path: Path) -> None:
        """Lower the current tile design into SAT-fab friendly BLIF.

        Parameters
        ----------
        bridge : PyosysBridge
            Yosys bridge holding the prepared tile design.
        blif_path : Path
            Destination BLIF path.
        """
        bridge.run_pass("aigmap")
        bridge.run_pass("techmap -map +/techmap.v")
        bridge.run_pass("opt -full")
        bridge.write_blif_path(blif_path)


def _bool_bit(value: int | bool) -> int:
    """Convert an integer-like config/control value to a one-bit constant.

    Parameters
    ----------
    value : int | bool
        Value to normalize.

    Returns
    -------
    int
        ``0`` or ``1``.
    """
    return int(bool(value))
