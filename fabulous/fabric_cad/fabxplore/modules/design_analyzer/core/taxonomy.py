"""Central taxonomy object for design analyzer classification.

This module defines canonical enum identifiers and encapsulates all family patterns,
report ordering, and characterization thresholds into one structured configuration
object.
"""

import re
from collections.abc import Mapping
from dataclasses import dataclass
from enum import StrEnum


class CellFamily(StrEnum):
    """Canonical identifiers for analyzer cell families."""

    MUX = "mux"
    ARITHMETIC = "arithmetic"
    CARRY = "carry"
    REDUCTION = "reduction"
    AND_LIKE = "and_like"
    OR_LIKE = "or_like"
    XOR_LIKE = "xor_like"
    COMPARE = "compare"
    LUT_LIKE = "lut_like"
    MEMORY = "memory"


class DesignTag(StrEnum):
    """Canonical identifiers for high-level design characterization tags."""

    SEQUENTIAL_HEAVY = "sequential-heavy"
    COMBINATIONAL_HEAVY = "combinational-heavy"
    ARITHMETIC_HEAVY = "arithmetic-heavy"
    CARRY_ACTIVE = "carry-active"
    MUX_HEAVY = "mux-heavy"
    MEMORY_ACTIVE = "memory-active"
    DEEP_BOOLEAN_CHAINS = "deep-boolean-chains"
    MIXED_STRUCTURE = "mixed-structure"


class ControlSignal(StrEnum):
    """Canonical identifiers for control-signal categories."""

    CLOCK = "clock"
    RESET = "reset"
    SET = "set"
    ENABLE = "enable"


@dataclass(frozen=True)
class CharacterizationThresholds:
    """Threshold bundle used to derive design characterization tags.

    Attributes
    ----------
    sequential_heavy : float
        Minimum sequential-cell ratio for ``SEQUENTIAL_HEAVY``.
    combinational_heavy : float
        Minimum combinational-cell ratio for ``COMBINATIONAL_HEAVY``.
    arithmetic_heavy : float
        Minimum arithmetic-family ratio for ``ARITHMETIC_HEAVY``.
    carry_active : float
        Minimum carry-family ratio for ``CARRY_ACTIVE``.
    mux_heavy : float
        Minimum mux-family ratio for ``MUX_HEAVY``.
    memory_active : float
        Minimum memory-cell ratio for ``MEMORY_ACTIVE``.
    unknown_warning : float
        Minimum unknown-cell ratio for uncertainty warnings.
    custom_warning_ratio : float
        Minimum custom-cell ratio for technology-specific warnings.
    deep_boolean_chain : int
        Minimum AND/OR chain depth for ``DEEP_BOOLEAN_CHAINS``.
    deep_mux_chain : int
        Minimum mux chain depth for mux-depth observations.
    """

    sequential_heavy: float = 0.45
    combinational_heavy: float = 0.75
    arithmetic_heavy: float = 0.14
    carry_active: float = 0.04
    mux_heavy: float = 0.18
    memory_active: float = 0.06
    unknown_warning: float = 0.25
    custom_warning_ratio: float = 0.15
    deep_boolean_chain: int = 8
    deep_mux_chain: int = 8


@dataclass(frozen=True)
class AnalyzerTaxonomy:
    """Container for all analyzer taxonomy data.

    Attributes
    ----------
    family_patterns : Mapping[CellFamily, tuple[re.Pattern[str], ...]]
        Regex patterns used to classify cell types into families.
    sequential_patterns : tuple[re.Pattern[str], ...]
        Regex patterns used to classify sequential cell types.
    report_family_order : tuple[CellFamily, ...]
        Family order for report tables.
    chain_families : tuple[CellFamily, ...]
        Families used for chain/connectivity analysis.
    control_port_prefixes : Mapping[ControlSignal, tuple[str, ...]]
        Prefix rules used to classify control ports.
    thresholds : CharacterizationThresholds
        Threshold bundle for characterization logic.
    """

    family_patterns: Mapping[CellFamily, tuple[re.Pattern[str], ...]]
    sequential_patterns: tuple[re.Pattern[str], ...]
    report_family_order: tuple[CellFamily, ...]
    chain_families: tuple[CellFamily, ...]
    control_port_prefixes: Mapping[ControlSignal, tuple[str, ...]]
    thresholds: CharacterizationThresholds


def build_default_taxonomy() -> AnalyzerTaxonomy:
    """Build the default analyzer taxonomy configuration.

    Returns
    -------
    AnalyzerTaxonomy
        Fully populated default taxonomy object.
    """
    family_patterns: dict[CellFamily, tuple[re.Pattern[str], ...]] = {
        CellFamily.MUX: (
            re.compile(r"^\$mux$"),
            re.compile(r"^\$pmux$"),
            re.compile(r"^\$bmux$"),
            re.compile(r"^\$demux$"),
            re.compile(r"^\$tribuf$"),
            re.compile(r"^\$_MUX_"),
            re.compile(r"^\$_NMUX_"),
            re.compile(r"^\$_MUX\d+_"),
            re.compile(r"^\$_TBUF_"),
        ),
        CellFamily.ARITHMETIC: (
            re.compile(r"^\$alu$"),
            re.compile(r"^\$fa$"),
            re.compile(r"^\$lcu$"),
            re.compile(r"^\$add$"),
            re.compile(r"^\$sub$"),
            re.compile(r"^\$mul$"),
            re.compile(r"^\$macc$"),
            re.compile(r"^\$div"),
            re.compile(r"^\$mod"),
            re.compile(r"^\$pow"),
            re.compile(r"CARRY", re.IGNORECASE),
            re.compile(r"ADDER", re.IGNORECASE),
            re.compile(r"ALU", re.IGNORECASE),
            re.compile(r"DSP", re.IGNORECASE),
        ),
        CellFamily.CARRY: (
            re.compile(r"^\$alu$"),
            re.compile(r"^\$fa$"),
            re.compile(r"^\$lcu$"),
            re.compile(r"^\$_FA_"),
            re.compile(r"CARRY", re.IGNORECASE),
            re.compile(r"\bLCU\b", re.IGNORECASE),
        ),
        CellFamily.REDUCTION: (
            re.compile(r"^\$reduce_"),
            re.compile(r"^\$logic_"),
            re.compile(r"^\$reduce_bool$"),
        ),
        CellFamily.AND_LIKE: (
            re.compile(r"^\$and$"),
            re.compile(r"^\$logic_and$"),
            re.compile(r"^\$reduce_and$"),
            re.compile(r"^\$_AND_"),
            re.compile(r"^\$_NAND_"),
            re.compile(r"^\$_ANDNOT_"),
            re.compile(r"^\$_AOI"),
        ),
        CellFamily.OR_LIKE: (
            re.compile(r"^\$or$"),
            re.compile(r"^\$logic_or$"),
            re.compile(r"^\$reduce_or$"),
            re.compile(r"^\$_OR_"),
            re.compile(r"^\$_NOR_"),
            re.compile(r"^\$_ORNOT_"),
            re.compile(r"^\$_OAI"),
        ),
        CellFamily.XOR_LIKE: (
            re.compile(r"^\$xor$"),
            re.compile(r"^\$xnor$"),
            re.compile(r"^\$reduce_xor$"),
            re.compile(r"^\$reduce_xnor$"),
            re.compile(r"^\$_XOR_"),
            re.compile(r"^\$_XNOR_"),
        ),
        CellFamily.COMPARE: (
            re.compile(r"^\$eq"),
            re.compile(r"^\$ne"),
            re.compile(r"^\$lt"),
            re.compile(r"^\$le"),
            re.compile(r"^\$gt"),
            re.compile(r"^\$ge"),
        ),
        CellFamily.LUT_LIKE: (
            re.compile(r"^\$lut$"),
            re.compile(r"^LUT\d+$"),
            re.compile(r"^FRAC_LUT", re.IGNORECASE),
        ),
        CellFamily.MEMORY: (
            re.compile(r"^\$mem"),
            re.compile(r"^\$memrd"),
            re.compile(r"^\$memwr"),
            re.compile(r"^\$meminit"),
            re.compile(r"^\$mem_v2$"),
        ),
    }

    sequential_patterns: tuple[re.Pattern[str], ...] = (
        re.compile(r"^\$dff"),
        re.compile(r"^\$adff"),
        re.compile(r"^\$sdff"),
        re.compile(r"^\$dffe"),
        re.compile(r"^\$ff$"),
        re.compile(r"^\$sr$"),
        re.compile(r"^\$dlatch"),
        re.compile(r"^\$adlatch"),
        re.compile(r"^\$dffsr"),
        re.compile(r"^\$dffsre"),
        re.compile(r"^\$_DFF"),
        re.compile(r"^\$_SDFF"),
        re.compile(r"^\$_DLATCH"),
        re.compile(r"^\$_SR_"),
    )

    report_family_order: tuple[CellFamily, ...] = (
        CellFamily.MUX,
        CellFamily.ARITHMETIC,
        CellFamily.CARRY,
        CellFamily.COMPARE,
        CellFamily.REDUCTION,
        CellFamily.AND_LIKE,
        CellFamily.OR_LIKE,
        CellFamily.XOR_LIKE,
        CellFamily.LUT_LIKE,
        CellFamily.MEMORY,
    )

    chain_families: tuple[CellFamily, ...] = (
        CellFamily.AND_LIKE,
        CellFamily.OR_LIKE,
        CellFamily.MUX,
        CellFamily.CARRY,
        CellFamily.ARITHMETIC,
    )

    control_port_prefixes: dict[ControlSignal, tuple[str, ...]] = {
        ControlSignal.CLOCK: ("C", "CLK", "CLOCK"),
        ControlSignal.RESET: ("R", "RST", "RESET", "ARST", "SRST", "CLR"),
        ControlSignal.SET: ("S", "SET", "PRE"),
        ControlSignal.ENABLE: ("EN", "CE", "E"),
    }

    return AnalyzerTaxonomy(
        family_patterns=family_patterns,
        sequential_patterns=sequential_patterns,
        report_family_order=report_family_order,
        chain_families=chain_families,
        control_port_prefixes=control_port_prefixes,
        thresholds=CharacterizationThresholds(),
    )


DEFAULT_TAXONOMY: AnalyzerTaxonomy = build_default_taxonomy()
