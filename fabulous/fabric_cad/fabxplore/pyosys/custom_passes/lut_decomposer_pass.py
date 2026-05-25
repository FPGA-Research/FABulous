"""Pyosys pass wrapper for high-LUT decomposition."""

from dataclasses import dataclass
from pathlib import Path

from fabulous.fabric_cad.fabxplore.modules.lut_decomposer.core.decomposer import (
    LutDecomposer,
)
from fabulous.fabric_cad.fabxplore.modules.lut_decomposer.core.models import (
    LutDecomposerResult,
)
from fabulous.fabric_cad.fabxplore.pyosys.pyosys_bridge import PyosysBridge
from fabulous.fabric_cad.fabxplore.pyosys.synth_pass import SynthPass
from fabulous.fabric_cad.fabxplore.utils.conf2bel import (
    apply_conf2bel_to_design,
    derive_conf2bel_from_verilog,
)


@dataclass
class LutDecomposerPass(SynthPass):
    """Decompose high-width LUTs into lower LUTs and a mux primitive.

    Attributes
    ----------
    source_lut_widths : list[int]
        Source ``$lut`` widths to decompose.
    leaf_lut_width : int
        Width of generated leaf ``$lut`` cofactors.
    mux_verilog_path : Path
        Verilog source containing the mux primitive.
    mux_top_name : str
        Mux primitive module name.
    mux_data_inputs : list[str]
        Candidate mux data input ports.
    mux_select_inputs : list[str]
        Candidate mux select input ports.
    mux_outputs : list[str]
        Candidate mux output ports.
    mux_configs : list[str] | None
        Explicit mux configuration input ports.
    mux_config_prefixes : list[str] | None
        Prefixes used to classify mux configuration inputs.
    mux_dependency_paths : list[Path] | None
        Additional Verilog files needed by the mux primitive.
    include_unused_mux_inputs : bool
        Whether unused mux inputs are tied to zero.
    max_decompositions : int | None
        Optional cap on successful decompositions.
    track_progress : bool
        Whether to log progress.
    progress_chunk_size : int
        Number of processed candidates between progress updates.
    top_name : str | None
        Top module to process.
    debug : bool
        Enable verbose pyosys output during internal mux compilation.
    conf2bel : bool
        Convert FABulous GLOBAL config-bit ports on emitted mux cells into
        BEL parameters and load a matching parameterized blackbox model.
    """

    source_lut_widths: list[int]
    leaf_lut_width: int
    mux_verilog_path: Path
    mux_top_name: str
    mux_data_inputs: list[str]
    mux_select_inputs: list[str]
    mux_outputs: list[str]
    mux_configs: list[str] | None = None
    mux_config_prefixes: list[str] | None = None
    mux_dependency_paths: list[Path] | None = None
    include_unused_mux_inputs: bool = False
    max_decompositions: int | None = None
    track_progress: bool = True
    progress_chunk_size: int = 100
    top_name: str | None = None
    debug: bool = False
    conf2bel: bool = False

    _result: LutDecomposerResult | None = None
    _verilog_model: str = ""

    def run_on(self, design: PyosysBridge) -> None:
        """Run the pass on a pyosys design.

        Parameters
        ----------
        design : PyosysBridge
            Design to mutate in place.
        """
        decomposer = LutDecomposer(
            source_lut_widths=self.source_lut_widths,
            leaf_lut_width=self.leaf_lut_width,
            mux_verilog_path=self.mux_verilog_path,
            mux_top_name=self.mux_top_name,
            mux_data_inputs=self.mux_data_inputs,
            mux_select_inputs=self.mux_select_inputs,
            mux_outputs=self.mux_outputs,
            mux_configs=self.mux_configs,
            mux_config_prefixes=self.mux_config_prefixes,
            mux_dependency_paths=self.mux_dependency_paths,
            include_unused_mux_inputs=self.include_unused_mux_inputs,
            max_decompositions=self.max_decompositions,
            track_progress=self.track_progress,
            progress_chunk_size=self.progress_chunk_size,
            debug=self.debug,
        )
        self._result = decomposer.map_from_design(
            design,
            top_name=self.top_name,
        )

        if self.conf2bel:
            conf2bel_model = derive_conf2bel_from_verilog(self.mux_verilog_path)
            apply_conf2bel_to_design(design, conf2bel_model)
            self._verilog_model = conf2bel_model.blackbox_verilog
        else:
            self._verilog_model = self.mux_verilog_path.read_text(encoding="utf-8")

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
    def result_data(self) -> LutDecomposerResult | None:
        """Return the latest structured result.

        Returns
        -------
        LutDecomposerResult | None
            Latest result if available.
        """
        return self._result

    @property
    def verilog_model(self) -> str:
        """Return the mux primitive Verilog model.

        Returns
        -------
        str
            Verilog text loaded after decomposition.
        """
        return self._verilog_model
