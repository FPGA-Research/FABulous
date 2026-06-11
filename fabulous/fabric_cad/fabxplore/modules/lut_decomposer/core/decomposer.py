"""Decompose high-width LUTs into leaf LUTs plus a solved mux primitive."""

from __future__ import annotations

from dataclasses import replace
from typing import TYPE_CHECKING

from fabulous.fabric_cad.fabxplore.modules.lut_decomposer.core.models import (
    LutCofactor,
    LutDecomposerCell,
    LutDecomposerDesign,
    LutDecomposerResult,
    LutDecomposerStats,
    LutDecomposition,
    MuxSolveKey,
)
from fabulous.fabric_cad.fabxplore.modules.lut_decomposer.core.mux_solver import (
    MuxShapeSolver,
)
from fabulous.fabric_cad.fabxplore.modules.lut_decomposer.core.process_tracker import (
    LutDecomposerProcessTracker,
)
from fabulous.fabric_cad.fabxplore.modules.lut_decomposer.core.reader import (
    LutDecomposerReader,
)
from fabulous.fabric_cad.fabxplore.modules.lut_decomposer.core.report import (
    render_lut_decomposer_report,
)
from fabulous.fabric_cad.fabxplore.modules.lut_decomposer.core.writer import (
    LutDecomposerWriter,
)
from fabulous.fabric_cad.fabxplore.modules.morph_tile.core.models import (
    ReplacementPortRef,
)

if TYPE_CHECKING:
    from pathlib import Path

    from fabulous.fabric_cad.fabxplore.pyosys.pyosys_bridge import PyosysBridge


class LutDecomposer:
    """Replace high-width ``$lut`` cells with leaf ``$lut`` cofactors and a mux.

    Parameters
    ----------
    source_lut_widths : list[int]
        Source LUT widths selected for decomposition.
    leaf_lut_width : int
        Width of generated cofactor LUTs.
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
        Explicit mux configuration inputs.
    mux_config_prefixes : list[str] | None
        Prefixes used to discover mux configuration inputs.
    mux_dependency_paths : list[Path] | None
        Additional Verilog files required by the mux primitive.
    include_unused_mux_inputs : bool
        Whether currently unused mux inputs should be tied to zero. Solved
        mux inputs are always connected.
    max_decompositions : int | None
        Optional cap on successful decompositions.
    track_progress : bool
        Whether to log progress.
    progress_chunk_size : int
        Number of processed candidates between progress messages.
    debug : bool
        Enable verbose pyosys output in internal mux compilation.
    """

    def __init__(
        self,
        source_lut_widths: list[int],
        leaf_lut_width: int,
        mux_verilog_path: Path,
        mux_top_name: str,
        mux_data_inputs: list[str],
        mux_select_inputs: list[str],
        mux_outputs: list[str],
        mux_configs: list[str] | None = None,
        mux_config_prefixes: list[str] | None = None,
        mux_dependency_paths: list[Path] | None = None,
        include_unused_mux_inputs: bool = False,
        max_decompositions: int | None = None,
        track_progress: bool = True,
        progress_chunk_size: int = 100,
        debug: bool = False,
    ) -> None:
        self.source_lut_widths = tuple(sorted(set(source_lut_widths)))
        self.leaf_lut_width = leaf_lut_width
        self.mux_top_name = mux_top_name
        self.mux_data_inputs = mux_data_inputs
        self.mux_select_inputs = mux_select_inputs
        self.mux_outputs = mux_outputs
        self.include_unused_mux_inputs = include_unused_mux_inputs
        self.max_decompositions = max_decompositions
        self._solver = MuxShapeSolver(
            mux_verilog_path=mux_verilog_path,
            mux_top_name=mux_top_name,
            mux_data_inputs=mux_data_inputs,
            mux_select_inputs=mux_select_inputs,
            mux_outputs=mux_outputs,
            mux_configs=mux_configs,
            mux_config_prefixes=mux_config_prefixes,
            mux_dependency_paths=mux_dependency_paths,
            debug=debug,
        )
        self._tracker = LutDecomposerProcessTracker(
            enabled=track_progress,
            chunk_size=progress_chunk_size,
        )

    def map_from_design(
        self,
        design: PyosysBridge,
        top_name: str | None = None,
    ) -> LutDecomposerResult:
        """Run decomposition on a live pyosys design.

        Parameters
        ----------
        design : PyosysBridge
            Design to mutate.
        top_name : str | None
            Top module to process. If ``None``, use the design top module.

        Returns
        -------
        LutDecomposerResult
            Applied decomposition result.
        """
        selected_top = top_name or design.top_name()
        decomposer_design = LutDecomposerReader().read_design(design, selected_top)
        result = self.plan(decomposer_design)
        LutDecomposerWriter(
            mux_top_name=self.mux_top_name,
            mux_inputs=[*self.mux_data_inputs, *self.mux_select_inputs],
            include_unused_mux_inputs=self.include_unused_mux_inputs,
            tracker=self._tracker,
        ).apply(design, result)
        return result

    def plan(self, design: LutDecomposerDesign) -> LutDecomposerResult:
        """Build a pure-Python decomposition plan.

        Parameters
        ----------
        design : LutDecomposerDesign
            Internal source design view.

        Returns
        -------
        LutDecomposerResult
            Decomposition plan and report.
        """
        selected = [
            cell for cell in design.lut_cells if cell.width in self.source_lut_widths
        ]
        self._tracker.start(len(selected))

        decompositions: list[LutDecomposition] = []
        failed = 0
        for cell in selected:
            if (
                self.max_decompositions is not None
                and len(decompositions) >= self.max_decompositions
            ):
                break
            decomposition = self._decompose_cell(cell)
            if decomposition is None:
                failed += 1
                self._tracker.record(replaced=False)
                continue
            decompositions.append(decomposition)
            self._tracker.record(replaced=True)

        self._tracker.done()
        stats = LutDecomposerStats(
            total_luts=len(design.lut_cells),
            candidate_luts=len(selected),
            decomposed_luts=len(decompositions),
            skipped_width_luts=len(design.lut_cells) - len(selected),
            failed_luts=failed,
            mux_solves=self._solver.solve_count,
            mux_cache_hits=self._solver.cache_hits,
            generated_leaf_luts=sum(len(item.cofactors) for item in decompositions),
        )
        result = LutDecomposerResult(
            top_name=design.top_name,
            source_lut_widths=self.source_lut_widths,
            leaf_lut_width=self.leaf_lut_width,
            decompositions=tuple(decompositions),
            stats=stats,
        )
        return replace(result, report_summary=render_lut_decomposer_report(result))

    def _decompose_cell(
        self,
        cell: LutDecomposerCell,
    ) -> LutDecomposition | None:
        """Build one decomposition if the mux shape is legal.

        Parameters
        ----------
        cell: LutDecomposerCell
            Source LUT cell from the internal design view.

        Returns
        -------
        LutDecomposition | None
            Decomposition plan, or ``None`` if the mux primitive cannot realize
            the needed shape.
        """
        if cell.width <= self.leaf_lut_width:
            return None

        select_width = cell.width - self.leaf_lut_width
        num_cofactors = 1 << select_width
        mux_result = self._solver.solve_shape(num_cofactors, select_width)
        if not mux_result.sat:
            return None

        cofactors = tuple(
            LutCofactor(
                index=index,
                init=_cofactor_init(
                    init=cell.init,
                    source_width=cell.width,
                    leaf_width=self.leaf_lut_width,
                    cofactor_index=index,
                ),
                cell_id=f"{cell.cell_id}__leaf_lut{index}",
                output_wire_id=f"{cell.cell_id}__leaf_lut{index}_out",
            )
            for index in range(num_cofactors)
        )
        return LutDecomposition(
            original_cell_id=cell.cell_id,
            source_width=cell.width,
            leaf_lut_width=self.leaf_lut_width,
            cofactors=cofactors,
            mux_cell_id=f"{cell.cell_id}__lut_decomp_mux",
            mux_input_ports=_mux_input_ports(
                mux_result.input_mapping,
                leaf_width=self.leaf_lut_width,
            ),
            mux_output_ports={
                mux_output: ReplacementPortRef.cell_port_bit("Y", 0)
                for mux_output in mux_result.output_mapping.values()
            },
            mux_config_bits=mux_result.config_bits,
            mux_shape=MuxSolveKey(
                data_inputs=num_cofactors,
                select_inputs=select_width,
            ),
        )


def _cofactor_init(
    init: int,
    source_width: int,
    leaf_width: int,
    cofactor_index: int,
) -> int:
    """Extract one leaf LUT cofactor INIT.

    Parameters
    ----------
    init : int
        Original source LUT INIT.
    source_width : int
        Original LUT width.
    leaf_width : int
        Leaf LUT width.
    cofactor_index : int
        Assignment of the high select inputs.

    Returns
    -------
    int
        Leaf LUT INIT.
    """
    _ = source_width
    leaf_init = 0
    high_offset = leaf_width
    for low_assignment in range(1 << leaf_width):
        source_index = low_assignment | (cofactor_index << high_offset)
        if (init >> source_index) & 1:
            leaf_init |= 1 << low_assignment
    return leaf_init


def _mux_input_ports(
    input_mapping: dict[str, str],
    leaf_width: int,
) -> dict[str, ReplacementPortRef]:
    """Translate SAT mux input mapping into writer references.

    Parameters
    ----------
    input_mapping : dict[str, str]
        Candidate mux input to abstract source mapping.
    leaf_width : int
        Number of low source LUT input bits.

    Returns
    -------
    dict[str, ReplacementPortRef]
        Mux input ports referenced to original cell ports or generated
        cofactor outputs.
    """
    refs = {}
    for mux_input, source in input_mapping.items():
        if source in {"0", "1"}:
            refs[mux_input] = ReplacementPortRef.const(int(source))
            continue
        if source.startswith("D") and source.removeprefix("D").isdigit():
            refs[mux_input] = ReplacementPortRef.cell_port_bit(
                f"__cofactor_{int(source.removeprefix('D'))}",
                0,
            )
            continue
        if source.startswith("S") and source.removeprefix("S").isdigit():
            refs[mux_input] = ReplacementPortRef.cell_port_bit(
                "A",
                leaf_width + int(source.removeprefix("S")),
            )
    return refs
