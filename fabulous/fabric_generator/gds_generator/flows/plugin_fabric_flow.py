"""Config-driven LibreLane plugin adapter for the FABulous fabric flow."""

from pathlib import Path

from librelane.config.variable import Variable
from librelane.flows.flow import Flow, FlowException

from fabulous.fabric_generator.code_generator.code_generator_Verilog import (
    VerilogCodeGenerator,
)
from fabulous.fabric_generator.gds_generator.flows.fabric_macro_flow import (
    FABulousFabricMacroFlow,
    _build_macros,
    _collect_fabric_verilog,
)
from fabulous.fabric_generator.gen_fabric.gen_fabric import generateFabric
from fabulous.fabric_generator.parser.parse_csv import parseFabricCSV


def _discover_tile_macros(
    tile_names: list[str], tile_library_paths: list[Path]
) -> dict[str, Path]:
    """Locate each tile's most recent ``RUN_*/final`` directory.

    Walks each ``FABULOUS_TILE_LIBRARY`` root, looks for ``<root>/<tile>/runs/``,
    and picks the most recently modified ``RUN_*/final`` directory. Tiles that
    cannot be resolved are omitted; the caller is responsible for surfacing
    the error.
    """
    discovered: dict[str, Path] = {}
    for tile in tile_names:
        candidates: list[Path] = []
        for lib in tile_library_paths:
            runs = Path(lib) / tile / "runs"
            if not runs.is_dir():
                continue
            candidates.extend(p for p in runs.glob("RUN_*/final") if p.is_dir())
        if not candidates:
            continue
        discovered[tile] = max(candidates, key=lambda p: p.stat().st_mtime)
    return discovered


@Flow.factory.register()
class FABulousFabric(FABulousFabricMacroFlow):
    """Drop-in replacement for ``librelane_plugin_fabulous.FABulousFabric``."""

    config_vars = FABulousFabricMacroFlow.config_vars + [
        Variable(
            "FABULOUS_FABRIC_CONFIG",
            list[Path],
            "Path to the fabric CSV describing the tile map, parameters, and "
            "per-tile CSV locations.",
        ),
        Variable(
            "FABULOUS_TILE_LIBRARY",
            list[Path],
            "List of paths to the tile library roots.",
        ),
        Variable(
            "FABULOUS_TILE_MACROS",
            dict[str, Path] | None,
            "Mapping of tile name to a previously-hardened macro output "
            "directory (containing ``metrics.json``, ``gds/``, ``lef/``, "
            "``vh/``, ``nl/``, ``pnl/``, ``spef/``). When omitted, each tile "
            "name in the fabric CSV is auto-resolved by scanning the "
            "``FABULOUS_TILE_LIBRARY`` paths for a ``<tile>/runs/RUN_*/final`` "
            "directory and picking the most recently-modified one.",
            default=None,
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

        fabric_csv_entries = self.config["FABULOUS_FABRIC_CONFIG"]
        if not fabric_csv_entries:
            raise FlowException("FABULOUS_FABRIC_CONFIG is empty")
        fabric_csv = Path(fabric_csv_entries[0])
        if not fabric_csv.is_file():
            raise FlowException(f"FABULOUS_FABRIC_CONFIG={fabric_csv} does not exist")
        self.fabric = parseFabricCSV(fabric_csv)
        design_name = self.config.get("DESIGN_NAME")
        if design_name is not None:
            self.fabric.name = design_name

        writer = VerilogCodeGenerator()
        writer.outFileName = fabric_csv.parent / "fabric.v"
        generateFabric(writer, self.fabric)

        # todo: use yaml instead of csv
        tile_macros_cfg = self.config.get("FABULOUS_TILE_MACROS") or {}
        tile_macro_dirs: dict[str, Path] = {
            name: Path(path) for name, path in dict(tile_macros_cfg).items()
        }
        if not tile_macro_dirs:
            tile_lib_paths = [
                Path(p) for p in self.config.get("FABULOUS_TILE_LIBRARY") or []
            ]
            tile_names = [
                t.name for t in self.fabric.tileDic.values() if not t.partOfSuperTile
            ]
            tile_macro_dirs = _discover_tile_macros(tile_names, tile_lib_paths)
        if not tile_macro_dirs:
            raise FlowException(
                "FABULOUS_TILE_MACROS is empty and no RUN_*/final directories "
                "were found under FABULOUS_TILE_LIBRARY. Either harden the "
                "tile macros first or supply FABULOUS_TILE_MACROS explicitly."
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
