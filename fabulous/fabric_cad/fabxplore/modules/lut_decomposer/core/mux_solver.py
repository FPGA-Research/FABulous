"""Solve mux primitive shapes for LUT decomposition."""

from __future__ import annotations

import re
from pathlib import Path
from tempfile import TemporaryDirectory

from fabulous.fabric_cad.fabxplore.modules.lut_decomposer.core.models import (
    MuxSolveKey,
    MuxSolveResult,
)
from fabulous.fabric_cad.fabxplore.modules.sat_fab import Circuit, Equiv
from fabulous.fabric_cad.fabxplore.pyosys.pyosys_bridge import PyosysBridge

_INDEXED_PORT_RE = re.compile(r"^(?P<base>.+)\[(?P<index>\d+)\]$")


class MuxShapeSolver:
    """Solve and cache mux primitive selection shapes.

    Parameters
    ----------
    mux_verilog_path : Path
        Verilog source containing the mux primitive.
    mux_top_name : str
        Top module name of the mux primitive.
    mux_data_inputs : list[str]
        Candidate data input port names.
    mux_select_inputs : list[str]
        Candidate select input port names. Vector ports may be given by base
        name, for example ``"S"`` for BLIF inputs ``S[0]`` and ``S[1]``.
    mux_outputs : list[str]
        Candidate output port names.
    mux_configs : list[str] | None
        Explicit configuration input ports.
    mux_config_prefixes : list[str] | None
        Prefixes used to classify configuration inputs.
    mux_dependency_paths : list[Path] | None
        Extra Verilog files needed to elaborate the mux primitive.
    debug : bool
        Enable verbose pyosys output while compiling the mux model.
    """

    def __init__(
        self,
        mux_verilog_path: Path,
        mux_top_name: str,
        mux_data_inputs: list[str],
        mux_select_inputs: list[str],
        mux_outputs: list[str],
        mux_configs: list[str] | None = None,
        mux_config_prefixes: list[str] | None = None,
        mux_dependency_paths: list[Path] | None = None,
        debug: bool = False,
    ) -> None:
        self.mux_verilog_path = mux_verilog_path
        self.mux_top_name = mux_top_name
        self.mux_data_inputs = mux_data_inputs
        self.mux_select_inputs = mux_select_inputs
        self.mux_outputs = mux_outputs
        self.mux_configs = mux_configs
        self.mux_config_prefixes = mux_config_prefixes
        self.mux_dependency_paths = mux_dependency_paths
        self.debug = debug
        self._candidate = self._build_candidate_circuit()
        self._candidate_inputs = self._selected_candidate_inputs()
        self._cache: dict[MuxSolveKey, MuxSolveResult] = {}
        self.solve_count = 0
        self.cache_hits = 0

    def solve_shape(
        self,
        num_data_inputs: int,
        num_select_inputs: int,
    ) -> MuxSolveResult:
        """Solve one abstract mux shape.

        Parameters
        ----------
        num_data_inputs : int
            Number of abstract data inputs.
        num_select_inputs : int
            Number of abstract select inputs.

        Returns
        -------
        MuxSolveResult
            SAT result and decoded mux route/config information.
        """
        key = MuxSolveKey(
            data_inputs=num_data_inputs,
            select_inputs=num_select_inputs,
        )
        cached = self._cache.get(key)
        if cached is not None:
            self.cache_hits += 1
            return MuxSolveResult(
                sat=cached.sat,
                input_mapping=dict(cached.input_mapping),
                output_mapping=dict(cached.output_mapping),
                config_bits=dict(cached.config_bits),
                cache_hit=True,
            )

        self.solve_count += 1
        spec_inputs = _spec_inputs(num_data_inputs, num_select_inputs)
        spec = Circuit.fast_lut(
            name="mux_shape_spec",
            inputs=spec_inputs,
            output="X",
            init=_mux_shape_init(num_data_inputs, num_select_inputs),
            reduce_lut_symmetry=False,
        )
        equiv_result = (
            Equiv.check(spec, self._candidate)
            .route_inputs(
                self._candidate,
                pool=spec_inputs,
                inputs=self._candidate_inputs,
                allow_reuse=True,
                allow_constants=False,
            )
            .route_outputs(
                self._candidate,
                {"X": self.mux_outputs},
                allow_reuse=False,
            )
            .solve()
        )

        if not equiv_result.sat:
            result = MuxSolveResult(sat=False)
            self._cache[key] = result
            return result

        config = equiv_result.config_for(self._candidate)
        result = MuxSolveResult(
            sat=True,
            input_mapping=equiv_result.input_mapping(self._candidate),
            output_mapping=equiv_result.output_mapping(self._candidate),
            config_bits={
                name: config.external_value(name)
                for name in self._candidate.config_names()
            },
        )
        self._cache[key] = result
        return result

    def _build_candidate_circuit(self) -> Circuit:
        """Build the mux candidate circuit once.

        Returns
        -------
        Circuit
            Candidate circuit compiled from Verilog.
        """
        with TemporaryDirectory(prefix="lut_decomposer_mux_") as td:
            blif_path = Path(td) / "mux.blif"
            self._write_candidate_blif(blif_path)
            return Circuit.from_blif(
                blif_path,
                top=self.mux_top_name,
                configs=self.mux_configs,
                config_prefixes=self.mux_config_prefixes,
                outputs=self.mux_outputs,
            )

    def _write_candidate_blif(self, blif_path: Path) -> None:
        """Compile the mux Verilog model into BLIF.

        Parameters
        ----------
        blif_path : Path
            Destination BLIF path.
        """
        bridge = PyosysBridge(debug=self.debug)
        paths = [
            *self._effective_dependency_paths(),
            self.mux_verilog_path,
        ]
        bridge.read_verilog_paths(paths, replace_design=True)
        bridge.run_pass(f"prep -top {self.mux_top_name}")
        bridge.run_pass("aigmap")
        bridge.run_pass(f"synth -top {self.mux_top_name} -flatten")
        bridge.write_blif_path(blif_path)

    def _effective_dependency_paths(self) -> list[Path]:
        """Return explicit and auto-discovered mux dependency paths.

        Returns
        -------
        list[Path]
            Existing dependency paths to read before the mux model.
        """
        paths = list(self.mux_dependency_paths or [])
        project_models = self.mux_verilog_path.parents[2] / "Fabric" / "models_pack.v"
        if project_models.exists() and project_models not in paths:
            paths.append(project_models)
        return paths

    def _selected_candidate_inputs(self) -> list[str]:
        """Return candidate input ports used for SAT routing.

        Returns
        -------
        list[str]
            Expanded candidate input names.

        Raises
        ------
        RuntimeError
            If a requested mux input port is not present in the compiled model.
        """
        available = self._candidate.input_names()
        selected: list[str] = []
        for name in self.mux_data_inputs:
            if name not in available:
                raise RuntimeError(f"Mux data input '{name}' not found")
            selected.append(name)
        for name in self.mux_select_inputs:
            selected.extend(_expand_input_name(name, available))
        return selected


def _spec_inputs(num_data_inputs: int, num_select_inputs: int) -> list[str]:
    """Return abstract mux-shape input names.

    Parameters
    ----------
    num_data_inputs : int
        Number of abstract data inputs.
    num_select_inputs : int
        Number of abstract select inputs.

    Returns
    -------
    list[str]
        Spec input names.
    """
    return [
        *(f"D{i}" for i in range(num_data_inputs)),
        *(f"S{i}" for i in range(num_select_inputs)),
    ]


def _mux_shape_init(num_data_inputs: int, num_select_inputs: int) -> int:
    """Build the truth table for ``out = data[select]``.

    Parameters
    ----------
    num_data_inputs : int
        Number of selectable data inputs.
    num_select_inputs : int
        Number of select bits.

    Returns
    -------
    int
        LSB-first truth table INIT.
    """
    width = num_data_inputs + num_select_inputs
    init = 0
    for assignment in range(1 << width):
        select = 0
        for bit_index in range(num_select_inputs):
            if (assignment >> (num_data_inputs + bit_index)) & 1:
                select |= 1 << bit_index
        if select < num_data_inputs and ((assignment >> select) & 1):
            init |= 1 << assignment
    return init


def _expand_input_name(name: str, available: list[str]) -> list[str]:
    """Expand a scalar or vector-base candidate input name.

    Parameters
    ----------
    name : str
        Requested input name.
    available : list[str]
        Candidate circuit input names.

    Returns
    -------
    list[str]
        Matching candidate input names.

    Raises
    ------
    RuntimeError
        If no matching input exists.
    """
    if name in available:
        return [name]
    indexed: list[tuple[int, str]] = []
    for candidate in available:
        match = _INDEXED_PORT_RE.match(candidate)
        if match is not None and match.group("base") == name:
            indexed.append((int(match.group("index")), candidate))
    if not indexed:
        raise RuntimeError(f"Mux select input '{name}' not found")
    return [candidate for _index, candidate in sorted(indexed)]
