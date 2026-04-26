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
    FracLutCellParameters,
    LogicalLutCell,
    PackedCell,
    PairBinding,
)
from fabulous.fabric_cad.fabxplore.modules.lut_combinator.core.truth_table import (
    format_bits,
    remap_init_to_slot,
)
from fabulous.fabric_cad.fabxplore.modules.lut_combinator.core.verilog_model import (
    FracLutBehavioralModel,
)


@dataclass(frozen=True)
class FracLutArchitecture:
    """Describe a two-half fractional LUT architecture.

    Attributes
    ----------
    frac_lut_size: int
        Input size ``K`` of each internal LUT.
    num_shared_inputs: int
        Number of nominal shared input pins ``I*`` configured in the architecture.
    name: str
        Emitted mapped cell type name.
    use_select_as_data_in_pair_mode: bool
        Whether dual-LUT pair packing may use the otherwise fixed ``S`` pin as
        a data input. When enabled, pair mapping behaves as if it had one fewer
        shared input and one more private input per side, without increasing the
        external pin count. This option only affects dual-LUT pair mode; full
        LUT(K+1) mode still uses ``S`` as the output mux select.

    Notes
    -----
    The physical cell is modeled as two LUT(K) halves feeding a 2:1 mux:

    - ``O0`` = mux(``S``, ``L0``, ``L1``)
    - ``O1`` = direct ``L1``

    In normal dual-LUT pair mode, ``S`` is tied to ``0`` so ``O0`` is the
    independent output of ``L0`` and ``O1`` is the independent output of ``L1``.
    In full LUT(K+1) mode, ``S`` is driven by the source LUT's extra input and
    selects between the two LUT(K) truth-table halves.

    When ``use_select_as_data_in_pair_mode`` is enabled, dual-LUT pair mode can
    repurpose ``S`` as one extra private data input for ``L0`` when normal
    shared-input wiring is not sufficient. Normal pair binding is tried first.
    If that fails, the last nominal shared input is cut from ``L0`` and kept as
    a private input for ``L1``. For example, with ``K=4`` and
    ``num_shared_inputs=3``, normal pair mode can still use:

    - ``L0(I0, I1, I2, A0)``
    - ``L1(I0, I1, I2, B0)``

    If a pair needs select-as-data, mapping behaves like an effective
    ``num_shared_inputs=2`` architecture:

    - ``L0(I0, I1, A0, S)``
    - ``L1(I0, I1, B0, I2)``

    The emitted INIT values are remapped to this internal pin order, and
    metadata marks that select-as-data mode was used.

    INIT bits are addressed with slot pin 0 as the least-significant address
    bit. The internal LUT slot input order used for INIT remapping is:

    - Normal pair mode:
      - ``L0`` slot order: ``I0, I1, ..., I(S-1), A0, A1, ...``
      - ``L1`` slot order: ``I0, I1, ..., I(S-1), B0, B1, ...``
    - Select-as-data pair mode, when used:
      - ``L0`` slot order: ``I0, I1, ..., I(S-2), A0, A1, ..., S``
      - ``L1`` slot order: ``I0, I1, ..., I(S-2), B0, B1, ..., I(S-1)``
    - Single LUT mode:
      - the LUT is mapped into ``L0``
      - ``L0`` slot order: ``I0, I1, ..., I(S-1), A0, A1, ...``
      - ``L1`` is unused and has INIT zero
    - Full LUT(K+1) mode:
      - the last source LUT input is used as ``S``
      - the remaining K data inputs are mapped into both ``L0`` and ``L1``
        using the normal single-LUT slot order:
        ``I0, I1, ..., I(S-1), A0, A1, ...``
      - ``L0_INIT`` stores the source INIT slice for ``S=0``
      - ``L1_INIT`` stores the source INIT slice for ``S=1``
      - ``O0`` is selected as ``S ? L1 : L0``

    The Verilog model reverses the slot order when building the address
    concatenation. For example, slot order ``(I0, I1, I2, A0)`` becomes
    ``{A0, I2, I1, I0}``.
    """

    frac_lut_size: int
    num_shared_inputs: int
    name: str = "FRAC_LUT"
    use_select_as_data_in_pair_mode: bool = False

    def __post_init__(self) -> None:
        """Validate architecture dimensions at construction time.

        This guard runs once after dataclass initialization. It rejects impossible
        architecture settings early so later packing code can assume valid dimensions.
        """
        if self.frac_lut_size < 1:
            raise ValueError("frac_lut_size must be >= 1")
        if self.num_shared_inputs < 0 or self.num_shared_inputs > self.frac_lut_size:
            raise ValueError("num_shared_inputs must be in [0, frac_lut_size]")
        if self.use_select_as_data_in_pair_mode and self.num_shared_inputs < 1:
            raise ValueError(
                "use_select_as_data_in_pair_mode requires at least one shared input"
            )

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

    @property
    def pair_shared_inputs(self) -> int:
        """Return the effective shared input count used for pair packing.

        In select-as-data mode, dual-LUT pair packing cuts one nominal shared
        input. The cut input becomes private to L1, while the otherwise-unused
        external ``S`` pin becomes the matching private input on L0.

        Returns
        -------
        int
            Effective shared input count for dual-LUT pair mapping.
        """
        if self.use_select_as_data_in_pair_mode:
            return self.num_shared_inputs - 1
        return self.num_shared_inputs

    @property
    def pair_private_inputs_per_lut(self) -> int:
        """Return the effective private input count used for pair packing.

        Returns
        -------
        int
            Number of private pins per internal LUT in pair mode.
        """
        return self.frac_lut_size - self.pair_shared_inputs

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

        normal_binding = self._try_bind_pair_with_mode(
            lut0=lut0,
            lut1=lut1,
            shared_input_count=self.num_shared_inputs,
            private_input_count=self.private_inputs_per_lut,
            select_as_data_used=False,
        )
        if normal_binding is not None:
            return normal_binding

        if not self.use_select_as_data_in_pair_mode:
            return None

        return self._try_bind_pair_with_mode(
            lut0=lut0,
            lut1=lut1,
            shared_input_count=self.pair_shared_inputs,
            private_input_count=self.pair_private_inputs_per_lut,
            select_as_data_used=True,
        )

    def _try_bind_pair_with_mode(
        self,
        lut0: LogicalLutCell,
        lut1: LogicalLutCell,
        shared_input_count: int,
        private_input_count: int,
        select_as_data_used: bool,
    ) -> PairBinding | None:
        """Attempt pair placement with one explicit pair-mode wiring shape.

        Parameters
        ----------
        lut0 : LogicalLutCell
            First logical LUT candidate.
        lut1 : LogicalLutCell
            Second logical LUT candidate.
        shared_input_count : int
            Number of shared inputs available in this attempted mode.
        private_input_count : int
            Number of private inputs per side available in this attempted mode.
        select_as_data_used : bool
            Whether this attempt uses the select-as-data wiring pattern.

        Returns
        -------
        PairBinding | None
            Fully specified binding when this mode can implement the pair.
        """
        # Remove duplicate nets while preserving order.
        uniq0: tuple[str, ...] = _ordered_unique(lut0.input_nets)
        uniq1: tuple[str, ...] = _ordered_unique(lut1.input_nets)

        shared_nets: tuple[str, ...] | None = self._select_shared_nets(
            uniq0,
            uniq1,
            shared_input_count=shared_input_count,
            private_input_count=private_input_count,
        )

        if shared_nets is None:
            return None

        shared_set: set[str] = set(shared_nets)
        priv0: list[str] = [n for n in uniq0 if n not in shared_set]
        priv1: list[str] = [n for n in uniq1 if n not in shared_set]

        if len(priv0) > private_input_count:
            return None
        if len(priv1) > private_input_count:
            return None

        private_sources0: tuple[str, ...] = self._pair_private_source_names(
            "A", "L0", select_as_data_used=select_as_data_used
        )
        private_sources1: tuple[str, ...] = self._pair_private_source_names(
            "B", "L1", select_as_data_used=select_as_data_used
        )

        pin_map0, src_map0 = self._build_input_map(
            lut0.input_nets,
            shared_nets,
            tuple(priv0),
            prefix="A",
            shared_input_count=shared_input_count,
            private_source_names=private_sources0,
        )
        pin_map1, src_map1 = self._build_input_map(
            lut1.input_nets,
            shared_nets,
            tuple(priv1),
            prefix="B",
            shared_input_count=shared_input_count,
            private_source_names=private_sources1,
        )

        # Build external pin mapping for all shared nets.
        ext_pins: dict[str, str] = {}
        for idx, net in enumerate(shared_nets):
            ext_pins[f"I{idx}"] = net

        # Build external pin mapping for private nets on each side.
        for idx, net in enumerate(priv0):
            ext_pins[private_sources0[idx]] = net
        for idx, net in enumerate(priv1):
            ext_pins[private_sources1[idx]] = net

        if select_as_data_used:
            # The output mux select is configured internally in this mode.
            # Tie data-only replacement pins when a placement does not need
            # them, keeping generated cells deterministic for tiny LUT pairs.
            ext_pins.setdefault("S", "0")
            ext_pins.setdefault(self._cut_shared_pin_name(), "0")
        else:
            # For dual-LUT packing we preserve LUT0 on O0 and LUT1 on O1.
            # Select stays fixed so O0 does not become data-dependent.
            ext_pins["S"] = "0"

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
            select_as_data_used=select_as_data_used,
            effective_shared_inputs=shared_input_count,
            cut_shared_index=(
                self.num_shared_inputs - 1 if select_as_data_used else -1
            ),
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
            shared_input_count=self.num_shared_inputs,
        )
        pin_map1, _ = self._build_input_map(
            data_inputs,
            shared_nets,
            priv,
            prefix="B",
            shared_input_count=self.num_shared_inputs,
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

        # How much LUT space is left.
        leftover_lut_width: int = self._leftover_lut_width(
            lut0_width=lut.width, lut1_width=0, shared_count=0
        )

        params: FracLutCellParameters = FracLutCellParameters(
            meta_data=(
                f"lut_mapping=single;"
                f"lut_width={lut.width};"
                f"leftover_lut_width={leftover_lut_width}"
            ),
            lut_size=self.frac_lut_size,
            num_shared_inputs=self.num_shared_inputs,
            l0_cell_id=lut.cell_id,
            l1_cell_id=(
                f"{lut.cell_id}__S1"
                if lut.width == self.frac_lut_size + 1
                else f"{lut.cell_id}__UNUSED"
            ),
            l0_init=format_bits(init0, 1 << self.frac_lut_size),
            l1_init=format_bits(init1, 1 << self.frac_lut_size),
            select_as_data_capable=self.use_select_as_data_in_pair_mode,
            select_as_data_used=False,
            effective_shared_inputs=self.pair_shared_inputs,
            cut_shared_index=(
                self.num_shared_inputs - 1
                if self.use_select_as_data_in_pair_mode
                else -1
            ),
            mux_select_config=0,
        )

        return PackedCell(
            packed_id=f"{self.name}_{lut.cell_id}",
            architecture_name=self.name,
            placements=(placement,),
            external_pin_nets=dict(sorted(ext_pins.items())),
            output_pin_nets={"O0": lut.output_net},
            parameters=params.as_dict(),
            frac_lut_parameters=params,
            leftover_lut_width=leftover_lut_width,
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

        # Count shared nets for reporting purposes.
        # This gives insight into the packing quality.
        u0: set[str] = set(_ordered_unique(binding.placement0.cell.input_nets))
        u1: set[str] = set(_ordered_unique(binding.placement1.cell.input_nets))
        shared_count: int = len(u0 & u1)

        lut0_width: int = binding.placement0.cell.width
        lut1_width: int = binding.placement1.cell.width

        # How much LUT space is left.
        leftover_lut_width: int = self._leftover_lut_width(
            lut0_width=lut0_width,
            lut1_width=lut1_width,
            shared_count=shared_count,
            architecture_shared_inputs=binding.effective_shared_inputs,
        )

        # Build parameters with original cell IDs and remapped INIT values.
        # For dual-LUT packing we keep the same cell IDs since both halves are needed.
        params: FracLutCellParameters = FracLutCellParameters(
            meta_data=(
                f"lut_mapping={self._pair_mapping_mode_name(binding)};"
                f"lut0_width={lut0_width};"
                f"lut1_width={lut1_width};"
                f"shared_inputs={shared_count};"
                f"leftover_lut_width={leftover_lut_width}"
                f"{self._select_as_data_meta_suffix(binding)}"
            ),
            lut_size=self.frac_lut_size,
            num_shared_inputs=self.num_shared_inputs,
            l0_cell_id=binding.placement0.cell.cell_id,
            l1_cell_id=binding.placement1.cell.cell_id,
            l0_init=format_bits(init0, 1 << self.frac_lut_size),
            l1_init=format_bits(init1, 1 << self.frac_lut_size),
            select_as_data_capable=self.use_select_as_data_in_pair_mode,
            select_as_data_used=binding.select_as_data_used,
            effective_shared_inputs=binding.effective_shared_inputs,
            cut_shared_index=binding.cut_shared_index,
            mux_select_config=0,
        )

        return PackedCell(
            packed_id=mapped_id,
            architecture_name=self.name,
            placements=(binding.placement0, binding.placement1),
            external_pin_nets=binding.external_pin_nets,
            output_pin_nets=binding.output_pin_nets,
            parameters=params.as_dict(),
            frac_lut_parameters=params,
            leftover_lut_width=leftover_lut_width,
        )

    def _leftover_lut_width(
        self,
        lut0_width: int,
        lut1_width: int,
        shared_count: int,
        architecture_shared_inputs: int | None = None,
    ) -> int:
        """Calculate the leftover LUT width after packing two LUTs.

        The leftover LUT width tells us how much extra LUTs we could pack into
        the same macro. This is also a measure of how efficiently we are using the
        architecture's LUT slots.

        Note: real packing extra luts in the same macro is only possible
        when the second output of the macro is not used.

        Parameters
        ----------
        lut0_width : int
            The input width of the first LUT.
        lut1_width : int
            The input width of the second LUT.
        shared_count : int
            The number of shared inputs between the two LUTs.
        architecture_shared_inputs : int | None
            Shared-input capacity of the architecture variant being reported.
            If ``None``, uses the nominal architecture shared-input count.


        Returns
        -------
        int
            The leftover LUT width after packing.
        """
        N = self.frac_lut_size
        P = (
            self.num_shared_inputs
            if architecture_shared_inputs is None
            else architecture_shared_inputs
        )
        S = shared_count
        T = 2 * N - P
        return T - (lut0_width + lut1_width - min(S, P))

    def _build_input_map(
        self,
        inputs: tuple[str, ...],
        shared_nets: tuple[str, ...],
        private_nets: tuple[str, ...],
        prefix: str,
        shared_input_count: int,
        private_source_names: tuple[str, ...] | None = None,
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
        shared_input_count : int
            Number of shared slot positions in the architecture mode being
            mapped. Private slot indices start after this count.
        private_source_names : tuple[str, ...] | None
            Optional external source names aligned to private pin indices.
            If omitted, names are built from ``prefix``.

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
                p = shared_input_count + idx
                pin_map.append(p)
                if private_source_names is None:
                    src_map.append(f"{prefix}{idx}")
                else:
                    src_map.append(private_source_names[idx])

        return tuple(pin_map), tuple(src_map)

    def _select_shared_nets(
        self,
        uniq0: tuple[str, ...],
        uniq1: tuple[str, ...],
        shared_input_count: int,
        private_input_count: int,
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
        shared_input_count : int
            Number of shared pins available in this mapping mode.
        private_input_count : int
            Number of private pins available per LUT in this mapping mode.

        Returns
        -------
        tuple[str, ...] | None
            Shared net tuple of length ``num_shared_inputs`` if a valid
            assignment exists, otherwise ``None``.
        """
        k: int = self.frac_lut_size
        s: int = shared_input_count
        p: int = private_input_count

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

    def _pair_private_source_names(
        self,
        prefix: str,
        slot_name: str,
        select_as_data_used: bool | None = None,
    ) -> tuple[str, ...]:
        """Return external source names for pair-mode private slot pins.

        In select-as-data mode, pair mapping behaves as if one shared input is
        cut. The last effective private source on L0 is the external ``S`` pin,
        while the last effective private source on L1 is the cut shared pin.

        Parameters
        ----------
        prefix : str
            Normal private pin prefix, usually ``"A"`` or ``"B"``.
        slot_name : str
            Internal slot name, either ``"L0"`` or ``"L1"``.
        select_as_data_used : bool | None
            Whether to use select-as-data private source names. If ``None``,
            uses this architecture's global option for backward-compatible
            internal calls.

        Returns
        -------
        tuple[str, ...]
            External source names aligned to effective private pin indices.

        Raises
        ------
        ValueError
            If an unsupported slot_name is given.
        """
        normal_private_count: int = self.private_inputs_per_lut
        names: list[str] = [f"{prefix}{idx}" for idx in range(normal_private_count)]

        if select_as_data_used is None:
            select_as_data_used = self.use_select_as_data_in_pair_mode

        if not select_as_data_used:
            return tuple(names)

        if slot_name == "L0":
            names.append("S")
        elif slot_name == "L1":
            names.append(self._cut_shared_pin_name())
        else:
            raise ValueError(f"Unsupported slot_name: {slot_name}")

        return tuple(names)

    def _cut_shared_pin_name(self) -> str:
        """Return the nominal shared pin repurposed as private in cut mode."""
        return f"I{self.num_shared_inputs - 1}"

    def _pair_mapping_mode_name(self, binding: PairBinding) -> str:
        """Return the mapping-mode label used in packed-cell metadata."""
        if binding.select_as_data_used:
            return "dual_select_as_data"
        return "dual"

    def _select_as_data_meta_suffix(self, binding: PairBinding) -> str:
        """Return select-as-data metadata for pair cells."""
        if not self.use_select_as_data_in_pair_mode:
            return ""

        if not binding.select_as_data_used:
            return (
                f";select_as_data_capable=1"
                f";select_as_data_used=0"
                f";nominal_shared_inputs={self.num_shared_inputs}"
                f";effective_shared_inputs={binding.effective_shared_inputs}"
                f";cut_shared_index=-1"
                f";mux_select_config=0"
            )

        return (
            f";select_as_data_capable=1"
            f";select_as_data_used=1"
            f";nominal_shared_inputs={self.num_shared_inputs}"
            f";effective_shared_inputs={binding.effective_shared_inputs}"
            f";cut_shared_index={binding.cut_shared_index}"
            f";s_data_side=L0"
            f";cut_shared_side=L1"
            f";mux_select_config=0"
        )

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

    def build_behavioral_model(
        self,
        interface_width: int | None = None,
        include_equiv_compat_params: bool = False,
    ) -> FracLutBehavioralModel:
        """Build the behavioral Verilog model for this FRAC LUT architecture.

        Parameters
        ----------
        interface_width : int | None
            Optional number of shared/private side ports to expose in the
            generated model. If ``None``, the model exposes only the nominal
            architecture ports. Equivalence tests may pass a wider value to
            tolerate named-port instances from different generated netlists.
        include_equiv_compat_params : bool
            Whether to include legacy/full-LUT compatibility parameters used
            by the standalone equivalence checker.

        Returns
        -------
        FracLutBehavioralModel
            Behavioral Verilog model configured from this architecture.
        """
        return FracLutBehavioralModel(
            name=self.name,
            lut_size=self.frac_lut_size,
            num_shared_inputs=self.num_shared_inputs,
            interface_width=interface_width,
            include_equiv_compat_params=include_equiv_compat_params,
        )


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
