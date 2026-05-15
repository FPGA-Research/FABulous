"""Pyosys pass wrapper for FF materialization."""

from dataclasses import dataclass
from pathlib import Path

from fabulous.fabric_cad.fabxplore.modules.ff_materializer.core.materializer import (
    FfMaterializer,
)
from fabulous.fabric_cad.fabxplore.modules.ff_materializer.core.models import (
    FfMaterializerResult,
    FfPortsInputAlias,
    LaneInput,
)
from fabulous.fabric_cad.fabxplore.modules.reg_absorber.core.models import (
    ConfigValue,
)
from fabulous.fabric_cad.fabxplore.pyosys.pyosys_bridge import PyosysBridge
from fabulous.fabric_cad.fabxplore.pyosys.synth_pass import SynthPass


@dataclass
class FfMaterializerPass(SynthPass):
    """Replace standalone FFs with configured tile register lanes.

    Attributes
    ----------
    tile_verilog_path : Path
        Verilog source file containing the replacement tile module.
    tile_top_name : str
        Module name to instantiate for replacements.
    tile_inputs : list[str]
        Scalar tile input ports exposed to the pass.
    tile_outputs : list[str]
        Scalar tile output ports exposed to the pass.
    lanes : list[LaneInput]
        Register lane definitions. Dicts are validated as pydantic models.
    tile_configs : list[str] | None
        Explicit scalar tile configuration bits.
    tile_config_prefixes : list[str] | None
        Prefixes used to discover config bits from emitted BLIF.
    ff_ports : FfPortsInputAlias | None
        Supported FF cell mapping. ``None`` selects defaults.
    pack_multiple_ffs_per_tile : bool
        Whether multiple lanes may be filled in one replacement tile instance.
    auto_config : bool
        Whether SAT-fab should solve one shared identity-path config for each
        materialized lane set.
    auto_config_overwrites : dict[str, ConfigValue] | None
        Optional fixed config bits used as constraints when ``auto_config`` is
        enabled. Ignored when ``auto_config`` is disabled.
    max_replacements : int | None
        Optional cap on replaced FFs.
    fail_on_invalid_lane : bool
        Whether invalid lane definitions should raise instead of being ignored.
    fail_on_auto_config_unsat : bool
        Whether unsatisfiable auto-config attempts should raise.
    fail_on_pack_conflict : bool
        Whether config, parameter, or shared-port packing conflicts should raise.
    fail_on_unmaterialized_ff : bool
        Whether any supported FF left unreplaced should raise.
    track_progress : bool
        Whether progress should be logged.
    progress_chunk_size : int
        Number of processed FFs between progress updates.
    top_name : str | None
        Top module to process.
    """

    tile_verilog_path: Path
    tile_top_name: str
    tile_inputs: list[str]
    tile_outputs: list[str]
    lanes: list[LaneInput]
    tile_configs: list[str] | None = None
    tile_config_prefixes: list[str] | None = None
    ff_ports: FfPortsInputAlias | None = None
    pack_multiple_ffs_per_tile: bool = True
    auto_config: bool = False
    auto_config_overwrites: dict[str, ConfigValue] | None = None
    max_replacements: int | None = None
    fail_on_invalid_lane: bool = True
    fail_on_auto_config_unsat: bool = False
    fail_on_pack_conflict: bool = False
    fail_on_unmaterialized_ff: bool = False
    track_progress: bool = True
    progress_chunk_size: int = 100
    top_name: str | None = None

    _result: FfMaterializerResult | None = None
    _verilog_model: str = ""

    def run_on(self, design: PyosysBridge) -> None:
        """Run the pass on a design.

        Parameters
        ----------
        design : PyosysBridge
            Design to mutate in place.
        """
        materializer = FfMaterializer(
            tile_verilog_path=self.tile_verilog_path,
            tile_top_name=self.tile_top_name,
            tile_inputs=self.tile_inputs,
            tile_outputs=self.tile_outputs,
            lanes=self.lanes,
            tile_configs=self.tile_configs,
            tile_config_prefixes=self.tile_config_prefixes,
            ff_ports=self.ff_ports,
            pack_multiple_ffs_per_tile=self.pack_multiple_ffs_per_tile,
            auto_config=self.auto_config,
            auto_config_overwrites=self.auto_config_overwrites,
            max_replacements=self.max_replacements,
            fail_on_invalid_lane=self.fail_on_invalid_lane,
            fail_on_auto_config_unsat=self.fail_on_auto_config_unsat,
            fail_on_pack_conflict=self.fail_on_pack_conflict,
            fail_on_unmaterialized_ff=self.fail_on_unmaterialized_ff,
            track_progress=self.track_progress,
            progress_chunk_size=self.progress_chunk_size,
        )
        self._result = materializer.map_from_design(design, top_name=self.top_name)
        self._verilog_model = self.tile_verilog_path.read_text(encoding="utf-8")
        design.read_verilog_string(self._verilog_model, blackbox=True)

    @property
    def report_summary(self) -> str:
        """Return the latest report summary.

        Returns
        -------
        str
            Report text, or a placeholder if the pass has not run.
        """
        return self._result.report_summary if self._result else "No result available."

    @property
    def result_data(self) -> FfMaterializerResult | None:
        """Return the latest structured result.

        Returns
        -------
        FfMaterializerResult | None
            Latest result if available.
        """
        return self._result

    @property
    def verilog_model(self) -> str:
        """Return the tile Verilog model.

        Returns
        -------
        str
            Tile Verilog text loaded after replacement.
        """
        return self._verilog_model
