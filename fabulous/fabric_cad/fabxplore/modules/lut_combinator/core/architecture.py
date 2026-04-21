"""Paired fractional LUT architecture model.

This type of archtecture is designed to capture the constraints of packing two LUT(K)
into a single macro with 0 <= N <= K shared inputs and K-N private inputs per side. The
architecture provides the main pair-feasibility routine that checks if two logical LUTs
can be placed together and if so, produces a complete binding with all pin assignments
needed for macro emission.
"""

from dataclasses import dataclass

from fabulous.fabric_cad.fabxplore.modules.lut_combinator.core.models import (
    CellPlacement,
    LogicalLutCell,
    PackedCell,
    PairBinding,
)
from fabulous.fabric_cad.fabxplore.modules.lut_combinator.core.truth_table import (
    format_bits,
    remap_init_to_slot,
)


@dataclass(frozen=True)
class FracLutArchitecture:
    """Paired fractional LUT architecture.

    Attributes
    ----------
    frac_lut_size: int
        Input size ``K`` of each internal LUT.
    num_shared_inputs: int
        Number of shared input pins configured in the architecture.
    name: str
        Emitted mapped cell type name.

    Notes
    -----
    The architecture models two LUT(K) feeding a 2:1 mux:
    - ``O0`` = mux(``S``, ``L0``, ``L1``)
    - ``O1`` = direct ``L1``

    For dual-LUT packing ``S`` is tied low to preserve independent outputs.
    For full-LUT ``K+1`` packing ``S`` is driven by the LUT's extra input.
    """

    frac_lut_size: int
    num_shared_inputs: int
    name: str = "FRAC_LUT"

    def __post_init__(self) -> None:
        """Validate architecture dimensions at construction time.

        This guard runs once after dataclass initialization. It rejects impossible
        architecture settings early so later packing code can assume valid dimensions.
        """
        if self.frac_lut_size < 1:
            raise ValueError("frac_lut_size must be >= 1")
        if self.num_shared_inputs < 0 or self.num_shared_inputs > self.frac_lut_size:
            raise ValueError("num_shared_inputs must be in [0, frac_lut_size]")

    @property
    def private_inputs_per_lut(self) -> int:
        """Return the per-LUT private pin budget.

        The architecture exposes ``num_shared_inputs`` globally.
        The remaining internal LUT pins are private to each side.
        This value is used as a hard feasibility bound in pairing.

        Returns
        -------
        int
            Number of private pins per internal LUT:
            ``frac_lut_size - num_shared_inputs``.
        """
        return self.frac_lut_size - self.num_shared_inputs

    def try_bind_pair(
        self, lut0: LogicalLutCell, lut1: LogicalLutCell
    ) -> PairBinding | None:
        """Attempt to place two LUTs into one paired fractional cell.

        This is the main pair-feasibility routine.
        It chooses shared nets, assigns remaining nets to private
        pins, and creates a complete binding for macro emission.
        If any architectural constraint fails, it returns ``None``.

        Parameters
        ----------
        lut0 : LogicalLutCell
            First logical LUT candidate.
        lut1 : LogicalLutCell
            Second logical LUT candidate.

        Returns
        -------
        PairBinding | None
            Fully specified placement and pin wiring if feasible,
            otherwise ``None``.
        """
        if lut0.width > self.frac_lut_size:
            return None
        if lut1.width > self.frac_lut_size:
            return None

        # Remove duplicate nets while preserving order.
        uniq0: tuple[str, ...] = _ordered_unique(lut0.input_nets)
        uniq1: tuple[str, ...] = _ordered_unique(lut1.input_nets)

        shared_nets: tuple[str, ...] | None = self._select_shared_nets(uniq0, uniq1)

        if shared_nets is None:
            return None

        shared_set: set[str] = set(shared_nets)
        priv0: list[str] = [n for n in uniq0 if n not in shared_set]
        priv1: list[str] = [n for n in uniq1 if n not in shared_set]

        if len(priv0) > self.private_inputs_per_lut:
            return None
        if len(priv1) > self.private_inputs_per_lut:
            return None

        pin_map0, src_map0 = self._build_input_map(
            lut0.input_nets,
            shared_nets,
            tuple(priv0),
            prefix="A",
        )
        pin_map1, src_map1 = self._build_input_map(
            lut1.input_nets,
            shared_nets,
            tuple(priv1),
            prefix="B",
        )

        # Build external pin mapping for all shared nets.
        ext_pins: dict[str, str] = {}
        for idx, net in enumerate(shared_nets):
            ext_pins[f"I{idx}"] = net

        # Build external pin mapping for private nets on each side.
        for idx, net in enumerate(priv0):
            ext_pins[f"A{idx}"] = net
        for idx, net in enumerate(priv1):
            ext_pins[f"B{idx}"] = net

        # For dual-LUT packing we preserve LUT0 on O0 and LUT1 on O1.
        # Select stays fixed so O0 does not become data-dependent.
        sel_net: str = "0"
        ext_pins["S"] = sel_net

        # Build placements with internal slot pin mapping and source net names.
        plc0: CellPlacement = CellPlacement(
            cell=lut0,
            slot_name="L0",
            input_to_slot_pin=pin_map0,
            input_to_slot_source=src_map0,
        )
        plc1: CellPlacement = CellPlacement(
            cell=lut1,
            slot_name="L1",
            input_to_slot_pin=pin_map1,
            input_to_slot_source=src_map1,
        )

        # Output mapping preserves original LUT output nets on O0 and O1.
        return PairBinding(
            placement0=plc0,
            placement1=plc1,
            external_pin_nets=dict(sorted(ext_pins.items())),
            output_pin_nets={"O0": lut0.output_net, "O1": lut1.output_net},
        )

    def bind_single_lut(self, lut: LogicalLutCell) -> PackedCell | None:
        """Map one LUT(K) or LUT(K+1) into one FRAC cell.

        This path is used for both single LUTs and decomposed LUT(K+1) cells.
        It emits the same FRAC-style parameter naming used
        by pair mapping (``L0_*``/``L1_*``). For LUT(K+1), it decomposes by select
        and maps both halves into L0/L1. For LUT(K), it maps the function into
        L0 and leaves L1 as zero.

        For LUT(K+1), decomposition uses the last source input as select:
        - L0 computes f(data, S=0)
        - L1 computes f(data, S=1)
        - O0 is mux(S, L0, L1)

        Parameters
        ----------
        lut : LogicalLutCell
            Source LUT expected to have width ``<= frac_lut_size + 1``.

        Returns
        -------
        PackedCell | None
            Packed FRAC cell representation for the LUT, or ``None`` when
            the LUT cannot fit architecture limits.
        """
        if lut.width > self.frac_lut_size + 1:
            return None

        if lut.width == self.frac_lut_size + 1:
            data_inputs: tuple[str, ...] = tuple(lut.input_nets[: self.frac_lut_size])
            select_input: str = lut.input_nets[self.frac_lut_size]
            l0_raw, l1_raw = self._split_init_by_select(lut.init, self.frac_lut_size)
        else:
            data_inputs = tuple(lut.input_nets)
            select_input = "0"
            l0_raw = lut.init
            l1_raw = 0

        uniq: tuple[str, ...] = _ordered_unique(data_inputs)
        if len(uniq) > self.frac_lut_size:
            return None

        shared_count: int = min(self.num_shared_inputs, len(uniq))
        shared_nets: tuple[str, ...] = tuple(uniq[:shared_count])
        shared_set: set[str] = set(shared_nets)
        priv: tuple[str, ...] = tuple(n for n in uniq if n not in shared_set)

        if len(priv) > self.private_inputs_per_lut:
            return None

        pin_map0, src_map0 = self._build_input_map(
            data_inputs,
            shared_nets,
            priv,
            prefix="A",
        )
        pin_map1, _ = self._build_input_map(
            data_inputs,
            shared_nets,
            priv,
            prefix="B",
        )

        init0: int = remap_init_to_slot(
            init=l0_raw,
            src_width=len(data_inputs),
            input_to_slot_pin=pin_map0,
            slot_width=self.frac_lut_size,
        )
        init1: int = remap_init_to_slot(
            init=l1_raw,
            src_width=len(data_inputs),
            input_to_slot_pin=pin_map1,
            slot_width=self.frac_lut_size,
        )

        ext_pins: dict[str, str] = {}
        for idx, net in enumerate(shared_nets):
            ext_pins[f"I{idx}"] = net
        for idx, net in enumerate(priv):
            ext_pins[f"A{idx}"] = net
            ext_pins[f"B{idx}"] = net
        ext_pins["S"] = select_input

        placement: CellPlacement = CellPlacement(
            cell=lut,
            slot_name="L0",
            input_to_slot_pin=pin_map0,
            input_to_slot_source=src_map0,
        )

        params: dict[str, str] = {
            "LUT_SIZE": str(self.frac_lut_size),
            "NUM_SHARED_INPUTS": str(self.num_shared_inputs),
            "L0_CELL_ID": lut.cell_id,
            "L1_CELL_ID": (
                f"{lut.cell_id}__S1"
                if lut.width == self.frac_lut_size + 1
                else f"{lut.cell_id}__UNUSED"
            ),
            "L0_INIT": format_bits(init0, 1 << self.frac_lut_size),
            "L1_INIT": format_bits(init1, 1 << self.frac_lut_size),
        }

        return PackedCell(
            packed_id=f"{self.name}_{lut.cell_id}",
            architecture_name=self.name,
            placements=(placement,),
            external_pin_nets=dict(sorted(ext_pins.items())),
            output_pin_nets={"O0": lut.output_net},
            parameters=params,
        )

    def build_mapped_cell(self, mapped_id: str, binding: PairBinding) -> PackedCell:
        """Build a packed macro cell from a validated pair binding.

        This converts each logical LUT INIT into the macro slot space
        and packages parameters, external pin mapping, and outputs.

        Parameters
        ----------
        mapped_id : str
            Identifier to use for the emitted packed cell instance.
        binding : PairBinding
            Pair placement and pin assignment returned by
            :meth:`try_bind_pair`.

        Returns
        -------
        PackedCell
            Fully populated mapped macro cell payload.
        """
        init0: int = remap_init_to_slot(
            init=binding.placement0.cell.init,
            src_width=binding.placement0.cell.width,
            input_to_slot_pin=binding.placement0.input_to_slot_pin,
            slot_width=self.frac_lut_size,
        )
        init1: int = remap_init_to_slot(
            init=binding.placement1.cell.init,
            src_width=binding.placement1.cell.width,
            input_to_slot_pin=binding.placement1.input_to_slot_pin,
            slot_width=self.frac_lut_size,
        )

        # Build parameters with original cell IDs and remapped INIT values.
        # For dual-LUT packing we keep the same cell IDs since both halves are needed.
        params: dict[str, str] = {
            "LUT_SIZE": str(self.frac_lut_size),
            "NUM_SHARED_INPUTS": str(self.num_shared_inputs),
            "L0_CELL_ID": binding.placement0.cell.cell_id,
            "L1_CELL_ID": binding.placement1.cell.cell_id,
            "L0_INIT": format_bits(init0, 1 << self.frac_lut_size),
            "L1_INIT": format_bits(init1, 1 << self.frac_lut_size),
        }

        return PackedCell(
            packed_id=mapped_id,
            architecture_name=self.name,
            placements=(binding.placement0, binding.placement1),
            external_pin_nets=binding.external_pin_nets,
            output_pin_nets=binding.output_pin_nets,
            parameters=params,
        )

    def _build_input_map(
        self,
        inputs: tuple[str, ...],
        shared_nets: tuple[str, ...],
        private_nets: tuple[str, ...],
        prefix: str,
    ) -> tuple[tuple[int, ...], tuple[str, ...]]:
        """Map each logical input net to an internal slot pin index.

        The mapping preserves source input order and distinguishes
        whether each source net is driven from shared pins or from
        a private side namespace (``A*`` or ``B*``).

        Parameters
        ----------
        inputs : tuple[str, ...]
            Ordered source input nets of one logical LUT.
        shared_nets : tuple[str, ...]
            Nets assigned to architecture shared pins ``I*``.
        private_nets : tuple[str, ...]
            Nets assigned to private pins on this side.
        prefix : str
            Private-side source prefix, typically ``"A"`` or ``"B"``.

        Returns
        -------
        tuple[tuple[int, ...], tuple[str, ...]]
            Pair of aligned tuples:
            - slot pin indices per source input
            - slot source names (e.g. ``I0``, ``A0``)

        Raises
        ------
        ValueError
            If any input net is not found in either shared or private assignments.
        """
        shared_idx: dict[str, int] = {n: i for i, n in enumerate(shared_nets)}
        private_idx: dict[str, int] = {n: i for i, n in enumerate(private_nets)}
        pin_map: list[int] = []
        src_map: list[str] = []

        for net in inputs:
            if net in shared_idx:
                p = shared_idx[net]
                pin_map.append(p)
                src_map.append(f"I{p}")
            else:
                idx = private_idx.get(net)
                if idx is None:
                    raise ValueError(
                        f"Internal mapping error: net '{net}' "
                        f"not assigned to shared/private pins."
                    )
                p = self.num_shared_inputs + idx
                pin_map.append(p)
                src_map.append(f"{prefix}{idx}")

        return tuple(pin_map), tuple(src_map)

    def _select_shared_nets(
        self, uniq0: tuple[str, ...], uniq1: tuple[str, ...]
    ) -> tuple[str, ...] | None:
        """Choose shared nets that make both LUTs fit architectural limits.

        The chooser prefers as many true intersections as possible,
        then adds deterministic fillers from each side and union order.
        This keeps placement reproducible while maximizing feasibility.

        Parameters
        ----------
        uniq0 : tuple[str, ...]
            Unique ordered nets used by LUT0.
        uniq1 : tuple[str, ...]
            Unique ordered nets used by LUT1.

        Returns
        -------
        tuple[str, ...] | None
            Shared net tuple of length ``num_shared_inputs`` if a valid
            assignment exists, otherwise ``None``.
        """
        k: int = self.frac_lut_size
        s: int = self.num_shared_inputs
        p: int = self.private_inputs_per_lut

        if len(uniq0) > k or len(uniq1) > k:
            return None

        set0: set = set(uniq0)
        set1: set = set(uniq1)
        inter: tuple[str, ...] = tuple(n for n in uniq0 if n in set1)
        only0: tuple[str, ...] = tuple(n for n in uniq0 if n not in set1)
        only1: tuple[str, ...] = tuple(n for n in uniq1 if n not in set0)

        req0: int = max(0, len(uniq0) - p)
        req1: int = max(0, len(uniq1) - p)

        best: tuple[str, ...] | None = None

        for xi in range(min(len(inter), s), -1, -1):
            x0: int = max(0, req0 - xi)
            x1: int = max(0, req1 - xi)
            if x0 > len(only0) or x1 > len(only1):
                continue
            if xi + x0 + x1 > s:
                continue

            chosen: list[str] = list(inter[:xi]) + list(only0[:x0]) + list(only1[:x1])

            # Fill remaining shared slots deterministically from available union nets.
            union_order: list[str] = list(_ordered_unique((*uniq0, *uniq1)))
            for net in union_order:
                if len(chosen) >= s:
                    break
                if net not in chosen:
                    chosen.append(net)

            best: tuple[str, ...] | None = tuple(chosen)
            break

        return best

    def _split_init_by_select(self, init: int, data_width: int) -> tuple[int, int]:
        """Split a LUT(K+1) INIT into two LUT(K) INIT images.

        The returned pair corresponds to select ``S=0`` and ``S=1``
        slices over the same data input index space.

        Parameters
        ----------
        init : int
            Source truth table bits for a LUT with ``data_width + 1``
            inputs encoded as an integer.
        data_width : int
            Number of non-select data inputs ``K``.

        Returns
        -------
        tuple[int, int]
            ``(l0, l1)`` where ``l0`` is the ``S=0`` table and ``l1``
            is the ``S=1`` table.
        """
        l0: int = 0
        l1: int = 0
        for data_idx in range(1 << data_width):
            b0: int = (init >> data_idx) & 1
            b1: int = (init >> (data_idx | (1 << data_width))) & 1
            l0 |= b0 << data_idx
            l1 |= b1 << data_idx
        return l0, l1


def _ordered_unique(values: tuple[str, ...]) -> tuple[str, ...]:
    """Return unique values while preserving first-seen order.

    This helper behaves like an ordered set conversion for tuples.
    It is used before net assignment so deterministic ordering is
    preserved while duplicate source nets are removed.

    Parameters
    ----------
    values : tuple[str, ...]
        Input values that may contain duplicates.

    Returns
    -------
    tuple[str, ...]
        Duplicate-free tuple with stable first-occurrence order.
    """
    seen: set[str] = set()
    out: list[str] = []
    for v in values:
        if v in seen:
            continue
        seen.add(v)
        out.append(v)
    return tuple(out)
