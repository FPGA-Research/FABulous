"""Typed data models for techmap-based chain mapping.

The chain mapper is configured through immutable dataclasses so the pyosys pass, core
mapper, report renderer, and per-cell techmap renderers all share the same view of the
run. This module intentionally contains no Yosys execution logic; it only defines
supported operation names, ALU INIT modes, configuration values, and structured
result/statistics objects.
"""

from dataclasses import dataclass, field
from enum import StrEnum


class ChainOp(StrEnum):
    """Supported Yosys cell families that can be mapped to ``__chain``.

    Attributes
    ----------
    ALU
        Map normalized ``$alu`` cells to per-bit ADD chain primitives.
    REDUCE_AND
        Map ``$reduce_and`` cells to reduction chains.
    REDUCE_OR
        Map ``$reduce_or`` cells to reduction chains.
    REDUCE_XOR
        Map ``$reduce_xor`` cells to reduction chains.
    REDUCE_BOOL
        Map ``$reduce_bool`` cells to OR-like reduction chains.
    """

    ALU = "alu"
    REDUCE_AND = "reduce_and"
    REDUCE_OR = "reduce_or"
    REDUCE_XOR = "reduce_xor"
    REDUCE_BOOL = "reduce_bool"


class AluInitMode(StrEnum):
    """INIT encoding style used for emitted ``$alu`` chain instances.

    Attributes
    ----------
    XOR
        Use a two-input local INIT for ``A ^ B`` and keep carry state in
        ``CI``/``CO``.
    FULL_ADDER
        Use a three-input local INIT for the full-adder sum over carry, ``A``,
        and ``B``.
    """

    XOR = "xor"
    FULL_ADDER = "full_adder"


@dataclass(frozen=True)
class ChainMapperConfig:
    """Configuration for one chain-mapper run.

    The config is shared by the pass wrapper, the core mapper, and each
    per-cell techmap renderer. It controls which Yosys cell families are
    lowered, how wide reduction chunks are, which normalization passes run
    before techmap, and how strict the chain primitive count limits are.

    Attributes
    ----------
    top_name : str
        Top module to analyze for reporting.
    chain_name : str
        Target-independent chain primitive name emitted by generated techmap.
    ops : tuple[ChainOp, ...]
        Yosys operation families to map.
    chunk_size : int
        Maximum number of reduction input bits absorbed by one chain primitive.
    min_chain_prims : int
        Minimum number of emitted chain primitives required before mapping a
        candidate cell. Shorter candidates are left untouched when possible.
    max_chain_prims : int | None
        Optional maximum number of chain primitives allowed for one candidate
        cell. Wider reductions or ALUs that would require more primitives are
        left untouched.
    and_to_or : bool
        Map ``$reduce_and`` through De Morgan using OR-mode chains.
    or_to_and : bool
        Map ``$reduce_or`` through De Morgan using AND-mode chains.
    leave_short : bool
        If ``True``, candidates shorter than ``min_chain_prims`` are left
        untouched. If ``False``, the mapper lowers the effective minimum to one
        primitive.
    normalize_extract_reduce : bool
        Run ``extract_reduce`` before techmap so gate-level AND/OR/XOR trees can
        become ``$reduce_*`` cells.
    normalize_alumacc : bool
        Run ``alumacc`` before techmap so arithmetic is normalized into
        ``$alu``/``$macc`` style cells.
    alu_init_mode : AluInitMode
        INIT encoding style for ``$alu`` chain primitive instances.
    read_chain_blackbox : bool
        Read a blackbox declaration for ``chain_name`` before techmap.
    run_clean : bool
        Run ``clean`` after generated techmap.
    debug_keep_techmap : bool
        Keep the generated techmap file path in the result and do not delete it.
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

    def __post_init__(self) -> None:
        """Validate configuration values."""
        if not self.chain_name:
            raise ValueError("chain_name must not be empty")
        if self.chunk_size < 1:
            raise ValueError("chunk_size must be >= 1")
        if self.min_chain_prims < 1:
            raise ValueError("min_chain_prims must be >= 1")
        if self.max_chain_prims is not None and self.max_chain_prims < 1:
            raise ValueError("max_chain_prims must be >= 1 when set")
        if not self.ops:
            raise ValueError("ops must not be empty")
        if any(not isinstance(op, ChainOp) for op in self.ops):
            raise TypeError("ops must contain only ChainOp values")
        if not isinstance(self.alu_init_mode, AluInitMode):
            raise TypeError("alu_init_mode must be an AluInitMode value")


@dataclass(frozen=True)
class ChainMapperStats:
    """Statistics collected before and after generated techmap.

    Attributes
    ----------
    before_counts : dict[str, int]
        Cell-type histogram in the configured top module before generated
        techmap is applied.
    after_counts : dict[str, int]
        Cell-type histogram in the configured top module after generated
        techmap and optional cleanup.
    commands : tuple[str, ...]
        Yosys commands executed by the chain mapper.
    generated_modules : tuple[str, ...]
        Names of generated techmap modules, one per selected cell renderer.
    """

    before_counts: dict[str, int] = field(default_factory=dict)
    after_counts: dict[str, int] = field(default_factory=dict)
    commands: tuple[str, ...] = ()
    generated_modules: tuple[str, ...] = ()

    @property
    def emitted_chain_prims(self) -> int:
        """Return the number of emitted chain primitive instances.

        Returns
        -------
        int
            Number of ``__chain`` cells present after mapping.
        """
        return self.after_counts.get("__chain", 0)


@dataclass(frozen=True)
class ChainMapperResult:
    """Result bundle produced by one chain mapper run.

    Attributes
    ----------
    top_name : str
        Top module name used for statistics and report rendering.
    chain_name : str
        Primitive name emitted by the generated techmap files.
    config : ChainMapperConfig
        Configuration used for the run.
    stats : ChainMapperStats
        Before/after cell counts, command log, and generated module names.
    techmap_verilog : str
        Concatenated generated techmap Verilog for inspection.
    techmap_path : str | None
        Single generated map path when exactly one file is kept for debugging.
    techmap_paths : tuple[str, ...]
        Generated map paths when ``debug_keep_techmap`` keeps multiple files.
    report_summary : str
        Human-readable report rendered from this result.
    """

    top_name: str
    chain_name: str
    config: ChainMapperConfig
    stats: ChainMapperStats
    techmap_verilog: str
    techmap_path: str | None = None
    techmap_paths: tuple[str, ...] = ()
    report_summary: str = ""
