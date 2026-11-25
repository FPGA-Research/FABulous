"""Delay values of the fabric timing model."""

from decimal import Decimal
from typing import NewType

Ns = NewType("Ns", Decimal)


def ns(value: float) -> Ns:
    """Return `value` in nanoseconds, keeping its Python `repr` text.

    The stored text is the printed text, so the placeholder `8`, the constant
    `3.0` and a characterised `0.123` print through one path. A float parsed from
    decimal text of at most 15 significant digits gets that exact value back.

    Parameters
    ----------
    value : float
        Delay in nanoseconds.

    Returns
    -------
    Ns
        The delay as an exact decimal.
    """
    return Ns(Decimal(repr(value)))
