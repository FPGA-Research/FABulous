"""Config-driven LibreLane plugin adapter for the FABulous fabric flow."""

from pathlib import Path

from librelane.config.variable import Variable
from librelane.flows.flow import Flow, FlowException

from fabulous.fabric_generator.gds_generator.flows.fabric_macro_flow import (
    FABulousFabricMacroFlow,
    _build_macros,
    _collect_fabric_verilog,
)
from fabulous.fabric_generator.parser.parse_csv import parseFabricCSV


@Flow.factory.register()
class FABulousFabric(FABulousFabricMacroFlow):
    """Drop-in replacement for ``librelane_plugin_fabulous.FABulousFabric``."""

    config_vars = FABulousFabricMacroFlow.config_vars + [
        Variable(
            "FABULOUS_FABRIC_CONFIG",
            Path,
            "Path to the fabric CSV describing the tile map, parameters, and "
            "per-tile CSV locations.",
        ),
        Variable(
            "FABULOUS_TILE_LIBRARY",
            Path | list[Path],
            "Path (or list of paths) to the tile library roots. Currently "
            "advisory: the fabric CSV is the authoritative source for tile "
            "locations. Accepted for standalone-plugin compatibility.",
        ),
        Variable(
            "FABULOUS_TILE_MACROS",
            dict[str, Path],
            "Mapping of tile name to a previously-hardened macro output "
            "directory (containing ``metrics.json``, ``gds/``, ``lef/``, "
            "``vh/``, ``nl/``, ``pnl/``, ``spef/``). Each entry is turned into "
            "a LibreLane ``Macro`` and referenced by the stitching flow.",
        ),
    ]

    def __init__(
        self,
        config: object = None,
        *,
        name: str | None = None,
        design_dir: str | None = None,
        pdk: str | None = None,
        pdk_root: str | None = None,
        **kwargs: object,
    ) -> None:
        # Skip FABulousFabricMacroFlow.__init__: plugin invocations receive a
        # plain LibreLane config and prepare fabric/macros here.
        super(FABulousFabricMacroFlow, self).__init__(
            config,
            name=name,
            design_dir=design_dir,
            pdk=pdk,
            pdk_root=pdk_root,
            **kwargs,
        )

        fabric_csv = Path(self.config["FABULOUS_FABRIC_CONFIG"])
        if not fabric_csv.is_file():
            raise FlowException(f"FABULOUS_FABRIC_CONFIG={fabric_csv} does not exist")
        self.fabric = parseFabricCSV(fabric_csv)

        tile_macro_dirs: dict[str, Path] = {
            name: Path(path)
            for name, path in dict(self.config["FABULOUS_TILE_MACROS"]).items()
        }
        if not tile_macro_dirs:
            raise FlowException(
                "FABULOUS_TILE_MACROS is empty. Provide a mapping of each "
                "fabric tile name to its pre-hardened macro directory."
            )

        self.macros, self.tile_sizes = _build_macros(tile_macro_dirs)

        if self.config.get("DESIGN_NAME") is None:
            self.config = self.config.copy(DESIGN_NAME=self.fabric.name)

        if "VERILOG_FILES" not in self.config or not self.config["VERILOG_FILES"]:
            fabric_verilog = _collect_fabric_verilog(
                fabric_csv.parent, self.fabric.name
            )
            self.config = self.config.copy(
                VERILOG_FILES=[str(p) for p in fabric_verilog]
            )
