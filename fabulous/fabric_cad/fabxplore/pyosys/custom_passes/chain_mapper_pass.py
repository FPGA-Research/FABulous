"""Pyosys custom pass wrapper for the techmap-based chain mapper."""

from dataclasses import dataclass

from fabulous.fabric_cad.fabxplore.modules.chain_mapper.core.mapper import (
    ChainMapper,
)
from fabulous.fabric_cad.fabxplore.modules.chain_mapper.core.models import (
    AluInitMode,
    ChainMapperConfig,
    ChainMapperResult,
    ChainOp,
)
from fabulous.fabric_cad.fabxplore.pyosys.pyosys_bridge import PyosysBridge
from fabulous.fabric_cad.fabxplore.pyosys.synth_pass import SynthPass


@dataclass
class ChainMapperPass(SynthPass):
    """Run generated techmap to lower selected cells to chain primitives.

    Attributes
    ----------
    top_name : str
        Top module name used for reports and cell-count histograms.
    chain_name : str
        Target-independent chain primitive name emitted by generated techmap.
    ops : tuple[ChainOp, ...]
        Operation families to map.
    chunk_size : int
        Number of reduction input bits absorbed by one chain primitive.
    min_chain_prims : int
        Minimum number of emitted chain primitives before mapping a candidate.
    max_chain_prims : int | None
        Optional maximum number of primitives allowed for one mapped cell.
    and_to_or : bool
        Map AND reductions through OR chains using De Morgan inversion.
    or_to_and : bool
        Map OR/BOOL reductions through AND chains using De Morgan inversion.
    leave_short : bool
        Leave candidates shorter than ``min_chain_prims`` untouched.
    normalize_extract_reduce : bool
        Run ``extract_reduce`` before generated techmap.
    normalize_alumacc : bool
        Run ``alumacc`` before generated techmap.
    alu_init_mode : AluInitMode
        INIT encoding mode for generated ``$alu`` chain instances.
    read_chain_blackbox : bool
        Read a blackbox declaration for ``chain_name`` before techmap.
    run_clean : bool
        Run ``clean`` after generated techmap.
    debug_keep_techmap : bool
        Keep the generated temporary techmap file for inspection.
    """

    top_name: str
    chain_name: str = "__chain"
    ops: tuple[ChainOp, ...] = (
        ChainOp.ALU,
        ChainOp.REDUCE_AND,
        ChainOp.REDUCE_OR,
        ChainOp.REDUCE_XOR,
        ChainOp.REDUCE_BOOL,
    )
    chunk_size: int = 4
    min_chain_prims: int = 2
    max_chain_prims: int | None = None
    and_to_or: bool = False
    or_to_and: bool = False
    leave_short: bool = True
    normalize_extract_reduce: bool = True
    normalize_alumacc: bool = True
    alu_init_mode: AluInitMode = AluInitMode.XOR
    read_chain_blackbox: bool = True
    run_clean: bool = True
    debug_keep_techmap: bool = False

    _verilog_model: str = ""
    _result: ChainMapperResult | None = None

    def run_on(self, design: PyosysBridge) -> None:
        """Run the pass on a pyosys design.

        Parameters
        ----------
        design : PyosysBridge
            Active design to mutate in place.
        """
        mapper = ChainMapper(
            ChainMapperConfig(
                top_name=self.top_name,
                chain_name=self.chain_name,
                ops=self.ops,
                chunk_size=self.chunk_size,
                min_chain_prims=self.min_chain_prims,
                max_chain_prims=self.max_chain_prims,
                and_to_or=self.and_to_or,
                or_to_and=self.or_to_and,
                leave_short=self.leave_short,
                normalize_extract_reduce=self.normalize_extract_reduce,
                normalize_alumacc=self.normalize_alumacc,
                alu_init_mode=self.alu_init_mode,
                read_chain_blackbox=self.read_chain_blackbox,
                run_clean=self.run_clean,
                debug_keep_techmap=self.debug_keep_techmap,
            )
        )
        self._result = mapper.map_from_design(design)
        self._verilog_model = self._result.verilog_behavioral

    @property
    def report_summary(self) -> str:
        """Return the report summary from the latest run.

        Returns
        -------
        str
            Rendered report if available, otherwise a placeholder string.
        """
        return self._result.report_summary if self._result else "No result available."

    @property
    def result_data(self) -> ChainMapperResult | None:
        """Return the latest structured result.

        Returns
        -------
        ChainMapperResult | None
            Latest result if the pass has run.
        """
        return self._result

    @property
    def verilog_model(self) -> str:
        """Return the generated Verilog model from the latest run.

        Returns
        -------
        str
            Generated Verilog code if available, otherwise an empty string.
        """
        return self._verilog_model
