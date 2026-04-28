"""Typed model objects for architecture-aware LUT cost mapping.

The LUT mapper computes an ABC ``-luts`` cost vector from a fractional-LUT
architecture model. The model objects in this file keep that calculation
structured so reports and pyosys passes can consume the same data.
"""

from collections.abc import Sequence
from dataclasses import dataclass
from enum import StrEnum


class LutMapperBackend(StrEnum):
    """Supported Yosys ABC LUT mapping backends.

    Attributes
    ----------
    ABC
        Use the classic ``abc`` pass.
    ABC9
        Use the ``abc9`` pass. This is the default because it usually provides
        better FPGA mapping quality for LUT-oriented flows.
    """

    ABC = "abc"
    ABC9 = "abc9"


@dataclass(frozen=True)
class LutMapperConfig:
    """Configuration for one architecture-aware LUT mapping run.

    Attributes
    ----------
    base_lut_size : int
        Size ``K`` of the internal LUT fragments that the fractional macro
        contains.
    num_shared_inputs : int
        Nominal number of shared data inputs between the two internal LUT
        fragments.
    use_select_as_data_in_pair_mode : bool
        If ``True``, the cost model treats the pair mode as having one
        additional effective private input, matching the select-as-data
        pairing mode used by the LUT combinator.
    max_lut_size : int
        Largest LUT width that ABC is allowed to generate. The emitted
        ``-luts`` vector contains one cost for every width from ``1`` through
        this value.
    backend : LutMapperBackend
        Yosys backend used to consume the cost vector. The default is
        ``LutMapperBackend.ABC9``.
    sharing_penalty_factor : float
        Multiplier for the required-shared-input table. Larger values make
        pairs that need shared inputs less desirable.
    size_penalty_factor : float
        Multiplier for the unused-capacity table. Larger values make small
        LUT pairs less desirable and shift costs toward larger LUTs.
    pair_discount_strength : float
        Maximum discount applied to widths that are easy to pack into a
        two-LUT fractional macro. A value of ``0.5`` means an ideal width can
        approach half the base cost.
    larger_lut_base_multiplier : float
        Multiplicative growth factor for composed LUTs wider than
        ``base_lut_size``. Wider LUT costs are based on the emitted cost of
        ``LUT(base_lut_size)`` so ABC sees the intended relative cost ratio.
    larger_lut_discount_factor : float
        Per-extra-input discount applied to larger composed LUTs relative to
        the emitted base-LUT cost. Values below ``1.0`` make wide LUTs slightly
        cheaper than exact multiplication.
    cost_scale : int
        Base integer cost scale used for ABC. ``100`` keeps reports readable
        while leaving room for fractional model values before rounding.
    min_cost : int
        Minimum emitted cost for every LUT width.
    max_cost : int | None
        Optional maximum emitted cost for every LUT width.
    raw_cost_vector : tuple[int | float, ...] | None
        Optional direct ABC cost vector. If provided, all analytical tables are
        still reported, but the emitted cost vector ignores them. A one-entry
        vector is broadcast to ``max_lut_size``. Any other length must exactly
        match ``max_lut_size``.
    run_opt_lut : bool
        Whether to run ``opt_lut`` after the selected backend.
    run_clean : bool
        Whether to run ``clean`` after the selected backend and optional
        ``opt_lut``.
    debug : bool
        Debug flag used when a non-inplace mapping has to create a temporary
        ``PyosysBridge`` clone.
    """

    base_lut_size: int = 4
    num_shared_inputs: int = 3
    use_select_as_data_in_pair_mode: bool = False
    max_lut_size: int = 8
    backend: LutMapperBackend = LutMapperBackend.ABC9

    sharing_penalty_factor: float = 1.0
    size_penalty_factor: float = 1.0
    pair_discount_strength: float = 0.5

    larger_lut_base_multiplier: float = 2.0
    larger_lut_discount_factor: float = 0.9

    cost_scale: int = 100
    min_cost: int = 1
    max_cost: int | None = None
    raw_cost_vector: tuple[int | float, ...] | None = None

    run_opt_lut: bool = True
    run_clean: bool = True
    debug: bool = False

    def __post_init__(self) -> None:
        """Validate configuration values.

        Raises
        ------
        TypeError
            If any field has an invalid type.
        ValueError
            If any field has an invalid value (e.g. negative or zero where not allowed).
        """
        if not isinstance(self.backend, LutMapperBackend):
            raise TypeError("backend must be a LutMapperBackend value")
        if self.raw_cost_vector is not None and not isinstance(
            self.raw_cost_vector, tuple
        ):
            raise TypeError("raw_cost_vector must be a tuple when set")
        if self.base_lut_size < 1:
            raise ValueError("base_lut_size must be >= 1")
        if self.max_lut_size < 1:
            raise ValueError("max_lut_size must be >= 1")
        if self.num_shared_inputs < 0:
            raise ValueError("num_shared_inputs must be >= 0")
        if self.cost_scale < 1:
            raise ValueError("cost_scale must be >= 1")
        if self.min_cost < 1:
            raise ValueError("min_cost must be >= 1")
        if self.max_cost is not None and self.max_cost < self.min_cost:
            raise ValueError("max_cost must be >= min_cost")
        if not 0.0 <= self.pair_discount_strength <= 1.0:
            raise ValueError("pair_discount_strength must be between 0.0 and 1.0")
        if self.larger_lut_base_multiplier <= 0.0:
            raise ValueError("larger_lut_base_multiplier must be > 0.0")
        if self.larger_lut_discount_factor <= 0.0:
            raise ValueError("larger_lut_discount_factor must be > 0.0")
        if self.raw_cost_vector is not None and len(self.raw_cost_vector) == 0:
            raise ValueError("raw_cost_vector must not be empty")


@dataclass(frozen=True)
class LutCostVector:
    """ABC LUT cost vector indexed by LUT width.

    Attributes
    ----------
    costs : tuple[int, ...]
        Cost for ``LUT1`` at index ``0``, ``LUT2`` at index ``1``, and so on.
    raw_override_used : bool
        Whether this vector came from ``raw_cost_vector`` instead of the
        analytical architecture model.
    """

    costs: tuple[int, ...]
    raw_override_used: bool = False

    def cost_for_width(self, width: int) -> int:
        """Return the cost assigned to one LUT width.

        Parameters
        ----------
        width : int
            LUT width to query. Widths are one-based.

        Returns
        -------
        int
            Cost value for the given LUT width.

        Raises
        ------
        ValueError
            If the width is less than 1 or greater than the length of the cost vector.
        """
        if width < 1 or width > len(self.costs):
            raise ValueError(f"width must be in [1, {len(self.costs)}]")
        return self.costs[width - 1]

    def to_yosys_luts_arg(self) -> str:
        """Return the comma-separated value used by ``abc``/``abc9 -luts``.

        Returns
        -------
        str
            Comma-separated ABC LUT cost vector.
        """
        return ",".join(str(cost) for cost in self.costs)


@dataclass(frozen=True)
class LutMapperResult:
    """Result bundle produced by one LUT mapper run.

    Attributes
    ----------
    top_name : str
        Top-level module name associated with the mapped pyosys design.
    config : LutMapperConfig
        Configuration used for the run.
    effective_shared_inputs : int
        Shared-input count used for analytical pairability estimation.
    effective_private_inputs : int
        Effective private inputs per LUT side used for pairability estimation.
    pair_capacity : int
        Maximum unique input count accepted by a pair in the analytical model.
    widths : tuple[int, ...]
        LUT widths used for pair tables, from ``1`` through ``base_lut_size``.
    sharing_required_table : tuple[tuple[int, ...], ...]
        Matrix of required shared inputs for each pair of widths.
    size_penalty_table : tuple[tuple[float, ...], ...]
        Matrix of unused-capacity penalties before multiplication by the size
        penalty factor.
    combined_penalty_table : tuple[tuple[float, ...], ...]
        Matrix after applying sharing and size penalty factors.
    pairability_by_width : tuple[float, ...]
        Average pairability score for every width in ``widths``.
    cost_vector : LutCostVector
        Emitted ABC LUT cost vector.
    abc_command : str
        Exact ABC command run by the mapper.
    followup_commands : tuple[str, ...]
        Additional pyosys commands run after ABC.
    report_summary : str
        Human-readable report for this run.
    """

    top_name: str
    config: LutMapperConfig
    effective_shared_inputs: int
    effective_private_inputs: int
    pair_capacity: int
    widths: tuple[int, ...]
    sharing_required_table: tuple[tuple[int, ...], ...]
    size_penalty_table: tuple[tuple[float, ...], ...]
    combined_penalty_table: tuple[tuple[float, ...], ...]
    pairability_by_width: tuple[float, ...]
    cost_vector: LutCostVector
    abc_command: str
    followup_commands: tuple[str, ...]
    report_summary: str = ""


def normalize_raw_cost_vector(
    raw_cost_vector: Sequence[int | float],
    max_lut_size: int,
) -> tuple[int, ...]:
    """Normalize a user-provided raw ABC cost vector.

    Parameters
    ----------
    raw_cost_vector : Sequence[int | float]
        User-provided cost vector. A single value is broadcast to all widths;
        any other length must exactly match ``max_lut_size``.
    max_lut_size : int
        Number of widths that the normalized vector must contain.

    Returns
    -------
    tuple[int, ...]
        Normalized integer cost vector.

    Raises
    ------
    ValueError
        If the vector length is invalid or any value is less than one after
        rounding.
    """
    values = tuple(raw_cost_vector)
    if len(values) == 1:
        values = values * max_lut_size
    elif len(values) != max_lut_size:
        raise ValueError(
            "raw_cost_vector must contain exactly one value or exactly "
            f"max_lut_size={max_lut_size} values"
        )

    costs = tuple(int(round(value)) for value in values)
    if any(cost < 1 for cost in costs):
        raise ValueError("raw_cost_vector values must round to costs >= 1")
    return costs
