"""CNF helper encodings.

This module contains small Tseitin encodings used by the SAT fabric encoder.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from pysat.formula import CNF


def add_ite(cnf: CNF, sel: int, true_lit: int, false_lit: int, out: int) -> None:
    """Encode a two-input mux.

    Parameters
    ----------
    cnf : CNF
        Formula that receives the clauses.
    sel : int
        Selector variable.
    true_lit : int
        Variable selected when ``sel`` is true.
    false_lit : int
        Variable selected when ``sel`` is false.
    out : int
        Output variable equivalent to ``sel ? true_lit : false_lit``.
    """
    cnf.append([out, -sel, -true_lit])
    cnf.append([out, sel, -false_lit])
    cnf.append([-out, -sel, true_lit])
    cnf.append([-out, sel, false_lit])


def add_not(cnf: CNF, arg: int, out: int) -> None:
    """Encode Boolean negation.

    Parameters
    ----------
    cnf : CNF
        Formula that receives the clauses.
    arg : int
        Input variable.
    out : int
        Output variable equivalent to ``not arg``.
    """
    cnf.append([out, arg])
    cnf.append([-out, -arg])


def add_and(cnf: CNF, left: int, right: int, out: int) -> None:
    """Encode Boolean conjunction.

    Parameters
    ----------
    cnf : CNF
        Formula that receives the clauses.
    left : int
        First input variable.
    right : int
        Second input variable.
    out : int
        Output variable equivalent to ``left and right``.
    """
    cnf.append([-out, left])
    cnf.append([-out, right])
    cnf.append([-left, -right, out])


def add_or(cnf: CNF, left: int, right: int, out: int) -> None:
    """Encode Boolean disjunction.

    Parameters
    ----------
    cnf : CNF
        Formula that receives the clauses.
    left : int
        First input variable.
    right : int
        Second input variable.
    out : int
        Output variable equivalent to ``left or right``.
    """
    cnf.append([-left, out])
    cnf.append([-right, out])
    cnf.append([left, right, -out])


def add_xor(cnf: CNF, left: int, right: int, out: int) -> None:
    """Encode Boolean exclusive-or.

    Parameters
    ----------
    cnf : CNF
        Formula that receives the clauses.
    left : int
        First input variable.
    right : int
        Second input variable.
    out : int
        Output variable equivalent to ``left xor right``.
    """
    cnf.append([-left, -right, -out])
    cnf.append([left, right, -out])
    cnf.append([left, -right, out])
    cnf.append([-left, right, out])


def add_eq(cnf: CNF, left: int, right: int) -> None:
    """Encode equality between two variables.

    Parameters
    ----------
    cnf : CNF
        Formula that receives the clauses.
    left : int
        First variable.
    right : int
        Second variable.
    """
    cnf.append([-left, right])
    cnf.append([left, -right])


def force_const(cnf: CNF, var: int, value: bool) -> None:
    """Force a SAT variable to a constant value.

    Parameters
    ----------
    cnf : CNF
        Formula that receives the unit clause.
    var : int
        Variable to constrain.
    value : bool
        Boolean value to assign.
    """
    cnf.append([var if value else -var])


def add_exactly_one(cnf: CNF, vars_: list[int]) -> None:
    """Encode a simple pairwise exactly-one constraint.

    Parameters
    ----------
    cnf : CNF
        Formula that receives the clauses.
    vars_ : list[int]
        Variables of which exactly one must be true.

    Raises
    ------
    ValueError
        If ``vars_`` is empty.
    """
    if not vars_:
        raise ValueError("exactly-one needs at least one variable")
    cnf.append(vars_[:])
    for i, left in enumerate(vars_):
        for right in vars_[i + 1 :]:
            cnf.append([-left, -right])


def bits_to_int_lsb0(bits: list[bool]) -> int:
    """Convert LSB-first bits to an integer.

    Parameters
    ----------
    bits : list[bool]
        Boolean bits where index zero is the least significant bit.

    Returns
    -------
    int
        Integer represented by the bit vector.
    """
    value = 0
    for index, bit in enumerate(bits):
        if bit:
            value |= 1 << index
    return value
