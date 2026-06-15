"""Configuration models for gate-level RTL mapping.

This module defines the user-facing PDK input configuration consumed by the netlist
mapping flow. The model stores explicit synthesis inputs, such as RTL files and optional
Liberty edits, and derives PDK-specific file paths and cell names from the active
FABulous context.
"""

from pathlib import Path

from pydantic import BaseModel, computed_field

from fabulous.fabulous_settings import get_context


class PdkInputConfig(BaseModel):
    """Input configuration for PDK-aware gate-level mapping.

    Attributes
    ----------
    top_name : str
        Name of the top RTL module to synthesize and map.
    rtl_files : list[Path]
        Verilog RTL source files passed into the synthesis flow.
    sub_circuit_map_rules : list[str] | None
        Optional Yosys extract rules used to collapse mapped gates into custom
        sub-circuit cells.
    buffer_wire_insertion : bool
        If ``True``, insert buffers on wires using the PDK's minimum buffer
        cell.
    change_cell_types : dict[str, list[str]] | None
        Optional mapping from cell names to replacement cell type candidates.
    add_liberty_cells : list[str] | None
        Optional Liberty text fragments containing one or more ``cell`` blocks
        to append to the selected Liberty corner.
    inject_liberty_fragments : list[str] | None
        Optional library-level Liberty text fragments to inject into the
        selected Liberty corner. Unlike ``add_liberty_cells``, these fragments
        may contain supporting groups such as ``lu_table_template`` in addition
        to ``cell`` blocks.
    remove_liberty_cells : list[str] | None
        Optional Liberty cell names to remove from the selected Liberty corner.
    change_liberty_cell_area : dict[str, float] | None
        Optional mapping from Liberty cell name to replacement area value.
    gates : str
        String identifier for the type of gates used in the design.
        https://yosyshq.readthedocs.io/projects/yosys/en/latest/cmd/
        index_passes_techmap.html#cmd-abc
    """

    top_name: str
    rtl_files: list[Path]
    sub_circuit_map_rules: list[str] | None = None
    buffer_wire_insertion: bool = False
    change_cell_types: dict[str, list[str]] | None = None
    add_liberty_cells: list[str] | None = None
    inject_liberty_fragments: list[str] | None = None
    remove_liberty_cells: list[str] | None = None
    change_liberty_cell_area: dict[str, float] | None = None
    gates: str = "cmos"

    @computed_field
    @property
    def pdk_root(self) -> Path:
        """Return the root directory of the active PDK.

        Returns
        -------
        Path
            Absolute path to the active PDK root.

        Raises
        ------
        ValueError
            If no PDK is configured and the default IHP PDK path does not
            exist.
        """
        pdk: str | None = get_context().pdk

        if pdk is None:
            p = Path.home() / ".ciel/ihp-sg13g2/ihp-sg13g2"
            if p.exists():
                return p
            raise ValueError(
                "PDK root could not be determined. Please set the "
                "PDK in the context or ensure that the default path exists."
            )

        pdk_root: Path | None = get_context().pdk_root
        if pdk is not None and pdk_root is not None:
            pdk_root = Path.resolve(pdk_root / pdk).absolute()
        return pdk_root

    @computed_field
    @property
    def pdk(self) -> str:
        """Return the active PDK identifier.

        Returns
        -------
        str
            Context PDK name, or ``"ihp-sg13g2"`` when no PDK is configured.
        """
        return get_context().pdk or "ihp-sg13g2"

    @computed_field
    @property
    def liberty_corner_file(self) -> Path:
        """Return the default Liberty timing corner for the active PDK.

        Returns
        -------
        Path
            Path to the Liberty file used by Yosys mapping and statistics.

        Raises
        ------
        ValueError
            If the active PDK is not supported by this mapping flow.
        """
        match self.pdk:
            case "ihp-sg13g2":
                return (
                    self.pdk_root
                    / "libs.ref/sg13g2_stdcell/lib/sg13g2_stdcell_typ_1p20V_25C.lib"
                )
            case "sky130A" | "sky130B":
                return (
                    self.pdk_root
                    / "libs.ref/sky130_fd_sc_hd/lib/sky130_fd_sc_hd__tt_025C_1v80.lib"
                )
            case _:
                raise ValueError(f"Unsupported PDK: {self.pdk}")

    @computed_field
    @property
    def techmap_files(self) -> list[Path]:
        """Return Yosys technology map files for the active PDK.

        Returns
        -------
        list[Path]
            PDK-specific Verilog techmap files used after standard-cell mapping.

        Raises
        ------
        ValueError
            If the active PDK is not supported by this mapping flow.
        """
        match self.pdk:
            case "ihp-sg13g2":
                return [
                    self.pdk_root / "libs.tech/librelane/sg13g2_stdcell/latch_map.v",
                    self.pdk_root / "libs.tech/librelane/sg13g2_stdcell/tribuff_map.v",
                ]
            case "sky130A" | "sky130B":
                return [
                    self.pdk_root / "libs.tech/openlane/sky130_fd_sc_hd/latch_map.v",
                    self.pdk_root / "libs.tech/openlane/sky130_fd_sc_hd/tribuff_map.v",
                ]
            case _:
                raise ValueError(f"Unsupported PDK: {self.pdk}")

    @computed_field
    @property
    def tiehi_cell_and_port(self) -> str:
        """Return the high tie cell and port for Yosys ``hilomap``.

        Returns
        -------
        str
            String containing the tie-high cell name followed by its output
            port.

        Raises
        ------
        ValueError
            If the active PDK is not supported by this mapping flow.
        """
        match self.pdk:
            case "ihp-sg13g2":
                return "sg13g2_tiehi L_HI"
            case "sky130A" | "sky130B":
                return "sky130_fd_sc_hd__tiehi L_HI"
            case _:
                raise ValueError(f"Unsupported PDK: {self.pdk}")

    @computed_field
    @property
    def tielo_cell_and_port(self) -> str:
        """Return the low tie cell and port for Yosys ``hilomap``.

        Returns
        -------
        str
            String containing the tie-low cell name followed by its output port.

        Raises
        ------
        ValueError
            If the active PDK is not supported by this mapping flow.
        """
        match self.pdk:
            case "ihp-sg13g2":
                return "sg13g2_tielo L_LO"
            case "sky130A" | "sky130B":
                return "sky130_fd_sc_hd__tielo L_LO"
            case _:
                raise ValueError(f"Unsupported PDK: {self.pdk}")

    @computed_field
    @property
    def min_buf_cell_and_ports(self) -> str:
        """Return the minimum buffer cell and ports for Yosys ``insbuf``.

        Returns
        -------
        str
            String containing the buffer cell name followed by input and output
            ports.

        Raises
        ------
        ValueError
            If the active PDK is not supported by this mapping flow.
        """
        match self.pdk:
            case "ihp-sg13g2":
                return "sg13g2_buf_1 A X"
            case "sky130A" | "sky130B":
                return "sky130_fd_sc_hd__buf_1 A X"
            case _:
                raise ValueError(f"Unsupported PDK: {self.pdk}")
