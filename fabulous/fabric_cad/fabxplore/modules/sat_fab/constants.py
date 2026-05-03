"""Shared symbolic constants.

This module centralizes string-valued enums used across the SAT fabric package.
"""

from __future__ import annotations

from enum import StrEnum


class NodeKind(StrEnum):
    """Circuit node kinds.

    Attributes
    ----------
    CONST0:
        Constant false node.
    CONST1:
        Constant true node.
    NOT:
        Boolean inverter.
    AND:
        Boolean conjunction.
    OR:
        Boolean disjunction.
    XOR:
        Boolean exclusive-or.
    ITE:
        If-then-else mux node.
    LUT:
        Configurable LUT node.
    ROUTE:
        Configurable one-hot route mux.
    TTABLE:
        Fixed truth-table node.
    """

    CONST0 = "CONST0"
    CONST1 = "CONST1"
    NOT = "NOT"
    AND = "AND"
    OR = "OR"
    XOR = "XOR"
    ITE = "ITE"
    LUT = "LUT"
    ROUTE = "ROUTE"
    TTABLE = "TTABLE"


class ConfigKind(StrEnum):
    """Configuration key kinds.

    Attributes
    ----------
    INPUT:
        External configuration input.
    LUT:
        LUT INIT bit.
    ROUTE:
        Route selector bit.
    """

    INPUT = "INPUT"
    LUT = "LUT"
    ROUTE = "ROUTE"


class Role(StrEnum):
    """Default equivalence roles.

    Attributes
    ----------
    C1:
        Left side role.
    C2:
        Right side role.
    """

    C1 = "c1"
    C2 = "c2"
