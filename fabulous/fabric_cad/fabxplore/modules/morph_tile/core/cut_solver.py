"""Solve LUT cut implementation problems for morph tiles.

A morph tile is modeled as a configurable Verilog module. ``CutSolver`` checks
whether that module can implement a requested LUT truth table by converting the
module to BLIF, importing it through ``sat_fab``, and asking the SAT equivalence
engine to find input routes, an output route, and configuration bits.
"""

from pathlib import Path
from tempfile import TemporaryDirectory

from fabulous.fabric_cad.fabxplore.modules.morph_tile.core.models import (
    CutSolveResult,
)
from fabulous.fabric_cad.fabxplore.modules.sat_fab import Circuit, Equiv
from fabulous.fabric_cad.fabxplore.pyosys.pyosys_bridge import PyosysBridge


class CutSolver:
    """Check whether a Verilog morph tile can realize a LUT INIT.

    Parameters
    ----------
    verilog_path : Path
        Verilog source file that defines the candidate tile.
    top_name : str
        Top module name of the candidate tile.
    inputs : list[str]
        Candidate tile input ports that may be driven by logical LUT inputs.
    outputs : list[str]
        Candidate tile output ports that may implement the logical LUT output.
    configs : list[str] | None
        Explicit candidate tile configuration input ports.
    config_prefixes : list[str] | None
        Prefixes used to classify BLIF model inputs as configuration bits.
    max_truth_table_inputs : int
        Maximum ``.names`` input count accepted by the BLIF importer.
    debug : bool
        Enable verbose pyosys output while converting Verilog to BLIF.
    """

    def __init__(
        self,
        verilog_path: Path,
        top_name: str,
        inputs: list[str],
        outputs: list[str],
        configs: list[str] | None = None,
        config_prefixes: list[str] | None = None,
        max_truth_table_inputs: int = 12,
        debug: bool = False,
    ) -> None:
        self.verilog_path = verilog_path
        self.top_name = top_name
        self.inputs = inputs
        self.outputs = outputs
        self.configs = configs
        self.config_prefixes = config_prefixes
        self.max_truth_table_inputs = max_truth_table_inputs
        self.debug = debug
        self._candidate = self._build_candidate_circuit()

    def solve_lut(
        self,
        init: int,
        lut_size: int,
        allow_input_reuse: bool = True,
        allow_input_constants: bool = False,
        allow_output_reuse: bool = False,
    ) -> CutSolveResult:
        """Check whether the candidate tile can implement one LUT function.

        Parameters
        ----------
        init : int
            LSB-first LUT INIT value to implement.
        lut_size : int
            Number of logical LUT inputs. This is explicit because leading
            zeroes in ``init`` are otherwise ambiguous.
        allow_input_reuse : bool
            Whether multiple candidate tile inputs may use the same logical LUT
            input.
        allow_input_constants : bool
            Whether routed candidate tile inputs may be tied to constants.
        allow_output_reuse : bool
            Whether multiple logical outputs may use the same candidate output.
            This is mostly future-facing for multi-output cuts.

        Returns
        -------
        CutSolveResult
            SAT status plus decoded input, output, and config mappings.

        Raises
        ------
        ValueError
            If ``lut_size`` is invalid.
        """
        if lut_size < 0:
            raise ValueError("lut_size must be >= 0")

        spec_inputs: list[str] = [f"A{i}" for i in range(lut_size)]
        spec_output: str = "X"
        spec = Circuit.fast_lut(
            name="cut_spec",
            init=init,
            inputs=spec_inputs,
            output=spec_output,
        )

        equiv_result = (
            Equiv.check(spec, self._candidate)
            .route_inputs(
                self._candidate,
                pool=spec_inputs,
                inputs=self.inputs,
                allow_reuse=allow_input_reuse,
                allow_constants=allow_input_constants,
            )
            .route_outputs(
                self._candidate,
                {spec_output: self.outputs},
                allow_reuse=allow_output_reuse,
            )
            .solve()
        )

        if not equiv_result.sat:
            return CutSolveResult(sat=False, raw_result=equiv_result)

        config = equiv_result.config_for(self._candidate)
        config_bits = {
            name: config.external_value(name) for name in self._candidate.config_names()
        }
        return CutSolveResult(
            sat=True,
            input_mapping=equiv_result.input_mapping(self._candidate),
            scoped_input_mapping=equiv_result.input_mapping(
                self._candidate,
                scoped=True,
            ),
            output_mapping=equiv_result.output_mapping(self._candidate),
            scoped_output_mapping=equiv_result.output_mapping(
                self._candidate,
                scoped=True,
            ),
            config_bits=config_bits,
            raw_result=equiv_result,
        )

    def _build_candidate_circuit(self) -> Circuit:
        """Build the SAT-fab candidate circuit once for this solver.

        Returns
        -------
        Circuit
            Candidate circuit compiled from the configured Verilog tile.
        """
        with TemporaryDirectory(prefix="morph_tile_cut_") as td:
            blif_path: Path = Path(td) / "candidate.blif"
            self._write_candidate_blif(blif_path)
            return self._candidate_from_blif(blif_path)

    def _write_candidate_blif(self, blif_path: Path) -> None:
        """Convert the candidate Verilog tile to BLIF.

        Parameters
        ----------
        blif_path : Path
            Destination BLIF file.
        """
        bridge = PyosysBridge(debug=self.debug)
        bridge.read_verilog_paths([self.verilog_path], replace_design=True)
        bridge.run_pass(f"prep -top {self.top_name}")
        bridge.run_pass("aigmap")
        bridge.run_pass(f"synth -top {self.top_name} -flatten")
        bridge.write_blif_path(blif_path)

    def _candidate_from_blif(self, blif_path: Path) -> Circuit:
        """Load the generated BLIF into a SAT-fab circuit.

        Parameters
        ----------
        blif_path : Path
            BLIF file generated from the candidate tile.

        Returns
        -------
        Circuit
            Candidate circuit used by the SAT equivalence engine.
        """
        return Circuit.from_blif(
            blif_path,
            top=self.top_name,
            inputs=self.inputs,
            configs=self.configs,
            config_prefixes=self.config_prefixes,
            outputs=self.outputs,
            max_truth_table_inputs=self.max_truth_table_inputs,
        )
