"""Pyosys pass wrapper for morph-tile LUT replacement."""

from dataclasses import dataclass
from pathlib import Path

from fabulous.fabric_cad.fabxplore.modules.morph_tile.core.mapper import (
    MorphTileMapper,
)
from fabulous.fabric_cad.fabxplore.modules.morph_tile.core.models import (
    MorphTileResult,
)
from fabulous.fabric_cad.fabxplore.pyosys.pyosys_bridge import PyosysBridge
from fabulous.fabric_cad.fabxplore.pyosys.synth_pass import SynthPass


@dataclass
class MorphTilePass(SynthPass):
    """Replace compatible ``$lut`` cells with morph-tile instances.

    Attributes
    ----------
    tile_verilog_path : Path
        Verilog source file containing the morph-tile module.
    tile_top_name : str
        Module name to instantiate for replacements.
    tile_inputs : list[str]
        Candidate tile data input ports.
    tile_outputs : list[str]
        Candidate tile output ports.
    considered_lut_widths : list[int]
        LUT widths considered for replacement.
    tile_configs : list[str] | None
        Explicit tile configuration input ports.
    tile_config_prefixes : list[str] | None
        Prefixes used to classify BLIF inputs as configuration bits.
    include_unused_inputs : bool
        Whether tile inputs unused by the solved mapping are tied to zero.
    max_replacements : int | None
        Optional cap on successful replacements.
    map_luts_first : bool
        Whether to run a simple LUT mapping flow before replacement.
    lut_map_size : int | None
        Maximum LUT size for optional pre-mapping.
    allow_input_reuse : bool
        Whether SAT may map several tile inputs to the same LUT input.
    allow_input_constants : bool
        Whether SAT may tie tile inputs to constants.
    allow_output_reuse : bool
        Whether SAT may reuse tile outputs.
    use_canonical_cache : bool
        Whether to share cache entries across input-permutation-equivalent LUT
        INIT functions.
    canonical_cache_max_width : int
        Maximum LUT width where permutation canonicalization is attempted.
    track_progress : bool
        Whether to log morph-tile mapping progress.
    progress_chunk_size : int
        Number of processed candidate LUTs between progress updates.
    top_name : str | None
        Top module to process.
    debug : bool
        Enable verbose pyosys output in internal solver conversions.
    """

    tile_verilog_path: Path
    tile_top_name: str
    tile_inputs: list[str]
    tile_outputs: list[str]
    considered_lut_widths: list[int]
    tile_configs: list[str] | None = None
    tile_config_prefixes: list[str] | None = None
    include_unused_inputs: bool = False
    max_replacements: int | None = None
    map_luts_first: bool = False
    lut_map_size: int | None = None
    allow_input_reuse: bool = True
    allow_input_constants: bool = False
    allow_output_reuse: bool = False
    use_canonical_cache: bool = True
    canonical_cache_max_width: int = 6
    track_progress: bool = True
    progress_chunk_size: int = 50
    top_name: str | None = None
    debug: bool = False

    _result: MorphTileResult | None = None
    _verilog_model: str = ""

    def run_on(self, design: PyosysBridge) -> None:
        """Run the morph-tile pass on a design.

        Parameters
        ----------
        design : PyosysBridge
            Design to mutate in place.
        """
        mapper = MorphTileMapper(
            tile_verilog_path=self.tile_verilog_path,
            tile_top_name=self.tile_top_name,
            tile_inputs=self.tile_inputs,
            tile_outputs=self.tile_outputs,
            considered_lut_widths=self.considered_lut_widths,
            tile_configs=self.tile_configs,
            tile_config_prefixes=self.tile_config_prefixes,
            include_unused_inputs=self.include_unused_inputs,
            max_replacements=self.max_replacements,
            map_luts_first=self.map_luts_first,
            lut_map_size=self.lut_map_size,
            allow_input_reuse=self.allow_input_reuse,
            allow_input_constants=self.allow_input_constants,
            allow_output_reuse=self.allow_output_reuse,
            use_canonical_cache=self.use_canonical_cache,
            canonical_cache_max_width=self.canonical_cache_max_width,
            track_progress=self.track_progress,
            progress_chunk_size=self.progress_chunk_size,
            debug=self.debug,
        )
        self._result = mapper.map_from_design(
            design,
            top_name=self.top_name,
        )
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
    def result_data(self) -> MorphTileResult | None:
        """Return the latest structured result.

        Returns
        -------
        MorphTileResult | None
            Latest result if available.
        """
        return self._result

    @property
    def verilog_model(self) -> str:
        """Return the morph-tile Verilog model.

        Returns
        -------
        str
            Tile Verilog text loaded after replacement.
        """
        return self._verilog_model
