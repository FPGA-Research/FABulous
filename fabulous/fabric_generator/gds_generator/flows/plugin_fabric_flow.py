"""Drop-in LibreLane plugin wrapper for the FABulous fabric-stitching flow.

Exposes :class:`FABulousFabric`, a LibreLane-factory-compatible flow that
accepts the same ``FABULOUS_FABRIC_CONFIG`` / ``FABULOUS_TILE_LIBRARY``
config variables as the standalone LibreLane FABulous plugin and drives the existing
:class:`FABulousFabricMacroFlow` pipeline.

The underlying :class:`FABulousFabricMacroFlow` has a specialised ``__init__``
that takes pre-parsed ``Fabric``/macro objects. This wrapper overrides it so
the flow is entirely config-driven: provide a fabric CSV and a map of
``tile_name`` → pre-hardened macro directory, and LibreLane can construct and
run the flow from a plain ``config.yaml``.
"""

import json
from decimal import Decimal
from pathlib import Path
from typing import cast

from librelane.config.variable import Macro, Variable
from librelane.flows.flow import Flow, FlowException

from fabulous.fabric_generator.gds_generator.flows.fabric_macro_flow import (
    FABulousFabricMacroFlow,
)
from fabulous.fabric_generator.parser.parse_csv import parseFabricCSV


@Flow.factory.register()
class FABulousFabric(FABulousFabricMacroFlow):
    """Drop-in replacement for ``librelane_plugin_fabulous.FABulousFabric``.

    Inherits the step list, substitutions, and ``run()`` body from
    :class:`FABulousFabricMacroFlow`; overrides ``__init__`` to accept the
    standard LibreLane config-dict form so users can invoke it via
    ``librelane flow config.yaml``.
    """

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
        # Skip FABulousFabricMacroFlow.__init__; go directly to Classic/Flow init.
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


def _build_macros(
    tile_macro_dirs: dict[str, Path],
) -> tuple[dict[str, Macro], dict[str, tuple[Decimal, Decimal]]]:
    """Build ``Macro`` objects and size map from a tile-name → macro-dir mapping.

    Mirrors the loop in :meth:`FABulousFabricMacroFlow.__init__` so behaviour is
    byte-identical.
    """
    macros: dict[str, Macro] = {}
    tile_sizes: dict[str, tuple[Decimal, Decimal]] = {}

    for name, tile_macro_path in tile_macro_dirs.items():
        metrics_path = tile_macro_path / "metrics.json"
        if not metrics_path.is_file():
            raise FlowException(
                f"metrics.json not found under {tile_macro_path} for tile {name!r}"
            )

        die_area = json.loads(metrics_path.read_text(encoding="utf-8")).get(
            "design__die__bbox"
        )
        if die_area is None:
            raise FlowException(
                f"metrics.json for {name!r} is missing design__die__bbox"
            )
        _, _, width, height = [Decimal(m) for m in die_area.split(" ")]

        spef_dict: dict[str, list[Path]] = {}
        spef_root = tile_macro_path / "spef"
        if spef_root.is_dir():
            for corner in spef_root.iterdir():
                spef_dict[corner.name] = list(corner.glob("*.spef"))

        macros[name] = Macro(
            gds=cast("list", list((tile_macro_path / "gds").glob("*.gds"))),
            lef=cast("list", [str(p) for p in (tile_macro_path / "lef").glob("*.lef")]),
            vh=cast("list", [str(p) for p in (tile_macro_path / "vh").glob("*.vh")]),
            nl=cast("list", [str(p) for p in (tile_macro_path / "nl").glob("*.nl.v")]),
            pnl=cast(
                "list", [str(p) for p in (tile_macro_path / "pnl").glob("*.pnl.v")]
            ),
            spef=spef_dict,
        )
        tile_sizes[name] = (width, height)

    return macros, tile_sizes


def _collect_fabric_verilog(fabric_dir: Path, fabric_name: str) -> list[Path]:
    """Best-effort search for the fabric-level Verilog when not provided in config."""
    candidates = [
        fabric_dir / f"{fabric_name}.v",
        fabric_dir / "fabric.v",
        *fabric_dir.glob("*.v"),
    ]
    seen: set[Path] = set()
    result: list[Path] = []
    for c in candidates:
        p = c.resolve()
        if p.is_file() and p not in seen:
            seen.add(p)
            result.append(p)
    if not result:
        raise FlowException(
            f"No fabric Verilog found under {fabric_dir}. Either set "
            "VERILOG_FILES in config.yaml or place the fabric Verilog "
            f"(e.g. {fabric_name}.v) alongside fabric.csv."
        )
    return result
