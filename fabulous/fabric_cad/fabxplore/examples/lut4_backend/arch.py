"""FABulous Architecture Synthesizer.

Some backend area and timing Tests for the LUT4AB architecture.
"""

from __future__ import annotations

from pathlib import Path

from fabulous.fabric_cad.fabxplore.flow.architecture_synthesizer import (
    ArchitectureSynthesizer,
)


class FabulousArchitecture(ArchitectureSynthesizer):
    """Concrete implementation of the ArchitectureSynthesizer for FABulous.

    Parameters
    ----------
    debug : bool
        Enable debug mode for verbose logging and intermediate design dumps.
    """

    def __init__(self, debug: bool = False) -> None:
        super().__init__(debug=debug)

        self.x_root = Path(__file__).resolve().parents[2]
        self.my_root: Path = self.x_root / "examples" / "lut4_backend"
        self.out_dir: Path = self.my_root / "out"
        self.nextpnr_exec: Path = Path(
            "/home/hausding/Documents/FABulous/demo_master_thesis/"
            "nextpnr/build/nextpnr-generic"
        )
        self.sta_exec: Path = Path(
            "/home/hausding/Documents/FABulous/demo_master_thesis/sta/sta"
        )

    def build_tile(self, mode: str) -> None:
        """Run the tile generation, placement, and routing stages."""
        # Do backend timing analysis using the specified STA executable.
        # Optimize area and timing of the design using the netlist tool pass.
        result = None

        match mode:
            case "abc_all":
                result = self.netlist_tool_pass(
                    tile_name="LUT4AB",
                    gates="all",
                )
            case "abc_cmos":
                result = self.netlist_tool_pass(
                    tile_name="LUT4AB",
                    gates="cmos",
                )
            case "abc_cmos2":
                result = self.netlist_tool_pass(
                    tile_name="LUT4AB",
                    gates="cmos2",
                )
            case "abc_mux_and":
                result = self.netlist_tool_pass(
                    tile_name="LUT4AB",
                    gates="MUX,AND",
                )
            case "abc_cmos2_rem_compou_lib":
                result = self.netlist_tool_pass(
                    tile_name="LUT4AB",
                    gates="cmos2",
                    remove_liberty_cells=[
                        "sg13g2_a22oi_1",
                        "sg13g2_a21oi_1",
                        "sg13g2_o21ai_1",
                    ],
                )
            case "abc_cmos2_rem_mux4_lib":
                result = self.netlist_tool_pass(
                    tile_name="LUT4AB",
                    gates="cmos2",
                    remove_liberty_cells=[
                        "sg13g2_mux4_1",
                    ],
                )
            case "abc_cmos2_custom_cells":
                result = self.netlist_tool_pass(
                    tile_name="LUT4AB",
                    gates="cmos2",
                    sub_circuit_map_rules=[
                        (self.my_root / "extract_map.v").read_text()
                    ],
                    inject_liberty_fragments=[(self.my_root / "cells.lib").read_text()],
                )

            case "abc_cmos2_custom_cells_rem_mux4_lib":
                result = self.netlist_tool_pass(
                    tile_name="LUT4AB",
                    gates="cmos2",
                    sub_circuit_map_rules=[
                        (self.my_root / "extract_map.v").read_text()
                    ],
                    inject_liberty_fragments=[(self.my_root / "cells.lib").read_text()],
                    remove_liberty_cells=[
                        "sg13g2_mux4_1",
                    ],
                )

            case "abc_cmos2_custom_cells_mux2_rem_compou_lib":
                result = self.netlist_tool_pass(
                    tile_name="LUT4AB",
                    gates="cmos2",
                    sub_circuit_map_rules=[
                        (self.my_root / "extract_map.v").read_text()
                    ],
                    inject_liberty_fragments=[(self.my_root / "cells.lib").read_text()],
                    remove_liberty_cells=[
                        "sg13g2_a22oi_1",
                        "sg13g2_a21oi_1",
                        "sg13g2_o21ai_1",
                    ],
                )

        result.run_sta(
            clk_ports=["UserCLK"],
            period_ns=20.0,
            sta_exec=self.sta_exec,
        )

        print(result.stats)  # noqa: T201
        print(result.area)  # noqa: T201

        print(result.sta_report)  # noqa: T201
        print("\nExtracted slacks:")  # noqa: T201
        print(result.slacks)  # noqa: T201

    def run_flow(self) -> None:
        """Run the DSE loop over multiple benchmarks."""
        self.build_tile(mode="abc_cmos2_custom_cells_mux2_rem_compou_lib")
