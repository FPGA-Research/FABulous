"""Canonical LUT cache helpers for morph-tile mapping.

Morph-tile SAT solving can be reused across LUT functions that differ only by input pin
permutation. This module computes a canonical truth table for that equivalence class and
remaps solved input routes back to the original LUT pin order after a cached result is
reused.
"""

from dataclasses import dataclass, replace
from itertools import permutations

from fabulous.fabric_cad.fabxplore.modules.morph_tile.core.models import (
    CutSolveResult,
)


@dataclass(frozen=True)
class CanonicalLutFunction:
    """Describe a LUT function in canonical cache form.

    Attributes
    ----------
    width : int
        LUT input width.
    original_init : int
        INIT value from the original LUT.
    canonical_init : int
        Minimum INIT value found across input permutations.
    permutation : tuple[int, ...]
        Mapping from canonical input index to original input index.
    enabled : bool
        Whether canonicalization was active for this function.
    """

    width: int
    original_init: int
    canonical_init: int
    permutation: tuple[int, ...]
    enabled: bool

    @property
    def cache_key(self) -> tuple[int, int]:
        """Return the cache key used by the morph-tile mapper.

        Returns
        -------
        tuple[int, int]
            Width and canonical INIT.
        """
        return (self.width, self.canonical_init)


def canonicalize_lut_init(
    init: int,
    width: int,
    enabled: bool = True,
) -> CanonicalLutFunction:
    """Canonicalize a LUT INIT under input permutation.

    Parameters
    ----------
    init : int
        Original LSB-first LUT INIT.
    width : int
        LUT input width.
    enabled : bool
        If ``False``, return the identity canonical form.

    Returns
    -------
    CanonicalLutFunction
        Canonical INIT plus the permutation needed to map canonical inputs back
        to original LUT inputs.

    Raises
    ------
    ValueError
        If ``width`` is negative.
    """
    if width < 0:
        raise ValueError("width must be >= 0")

    identity = tuple(range(width))
    if not enabled or width <= 1:
        return CanonicalLutFunction(
            width=width,
            original_init=init,
            canonical_init=init,
            permutation=identity,
            enabled=enabled,
        )

    best_init = init
    best_permutation = identity
    for permutation in permutations(range(width)):
        permuted = permute_lut_init(init, width, permutation)
        if permuted < best_init:
            best_init = permuted
            best_permutation = tuple(permutation)

    return CanonicalLutFunction(
        width=width,
        original_init=init,
        canonical_init=best_init,
        permutation=best_permutation,
        enabled=enabled,
    )


def permute_lut_init(init: int, width: int, permutation: tuple[int, ...]) -> int:
    """Permute LUT input variables in an INIT value.

    ``permutation[i]`` is the original input index used by canonical input
    ``i``. For example, ``(1, 0)`` swaps a two-input truth table.

    Parameters
    ----------
    init : int
        Original LSB-first LUT INIT.
    width : int
        LUT input width.
    permutation : tuple[int, ...]
        Mapping from new input index to original input index.

    Returns
    -------
    int
        INIT value after applying the input permutation.

    Raises
    ------
    ValueError
        If ``permutation`` does not match ``width``.
    """
    if len(permutation) != width:
        raise ValueError("permutation length must match width")

    out = 0
    for new_index in range(1 << width):
        old_index = 0
        for new_bit_index, old_bit_index in enumerate(permutation):
            if (new_index >> new_bit_index) & 1:
                old_index |= 1 << old_bit_index
        if (init >> old_index) & 1:
            out |= 1 << new_index
    return out


def remap_cut_solve_result(
    result: CutSolveResult,
    canonical: CanonicalLutFunction,
) -> CutSolveResult:
    """Remap a canonical SAT solution to the original LUT pin order.

    Parameters
    ----------
    result : CutSolveResult
        SAT result for ``canonical.canonical_init``.
    canonical : CanonicalLutFunction
        Canonical form used for the solve.

    Returns
    -------
    CutSolveResult
        Result with input mappings rewritten to the original LUT input names.
    """
    if not result.sat or canonical.permutation == tuple(range(canonical.width)):
        return result

    return replace(
        result,
        input_mapping={
            key: _remap_source_name(value, canonical.permutation)
            for key, value in result.input_mapping.items()
        },
        scoped_input_mapping={
            key: _remap_source_name(value, canonical.permutation)
            for key, value in result.scoped_input_mapping.items()
        },
    )


def _remap_source_name(source: str, permutation: tuple[int, ...]) -> str:
    """Remap one source input name through a canonical permutation."""
    prefix, separator, leaf = source.rpartition("/")
    name = leaf if separator else source
    if not name.startswith("A"):
        return source
    index_text = name.removeprefix("A")
    if not index_text.isdigit():
        return source
    index = int(index_text)
    if index >= len(permutation):
        return source

    remapped = f"A{permutation[index]}"
    return f"{prefix}/{remapped}" if separator else remapped
