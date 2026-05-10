"""Input-permutation cache helpers for morph-tile truth-table specs.

The permutation cache groups fixed truth-table specs that differ only by input order. It
supports both normal single-output LUT specs and multi-output specs, such as fractional
LUT cells reconstructed into several named output INITs. Only input permutations are
considered; output names, output polarity, and input polarity remain unchanged.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from itertools import permutations
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from fabulous.fabric_cad.fabxplore.modules.morph_tile.core.models import (
        CutSolveResult,
    )


@dataclass(frozen=True)
class PermutedTruthTable:
    """Describe a truth-table spec in input-permutation cache form.

    Attributes
    ----------
    input_names : tuple[str, ...]
        Logical spec inputs in canonical position order.
    output_inits : dict[str, int]
        Original output INITs.
    canonical_output_inits : dict[str, int]
        Output INITs after applying the selected input permutation.
    permutation : tuple[int, ...]
        Mapping from canonical input index to original input index.
    enabled : bool
        Whether input-permutation canonicalization was active.
    """

    input_names: tuple[str, ...]
    output_inits: dict[str, int]
    canonical_output_inits: dict[str, int]
    permutation: tuple[int, ...]
    enabled: bool

    @property
    def cache_key(self) -> tuple[object, ...]:
        """Return the cache key for this canonical truth-table spec.

        Returns
        -------
        tuple[object, ...]
            Stable cache key for either permutation or exact-cache mode.
        """
        output_names = tuple(sorted(self.canonical_output_inits))
        output_values = tuple(
            self.canonical_output_inits[name] for name in output_names
        )
        if self.enabled:
            return ("permute", len(self.input_names), output_names, output_values)
        return ("exact", self.input_names, output_names, output_values)


def canonicalize_truth_table(
    input_names: list[str],
    output_inits: dict[str, int],
    enabled: bool = True,
) -> PermutedTruthTable:
    """Canonicalize output INITs under input permutation.

    Parameters
    ----------
    input_names : list[str]
        Logical spec input names.
    output_inits : dict[str, int]
        Output INITs keyed by output name.
    enabled : bool
        If ``False``, return the identity cache form.

    Returns
    -------
    PermutedTruthTable
        Canonical truth-table data and the remap permutation.

    Raises
    ------
    ValueError
        If no outputs are provided.
    """
    if not output_inits:
        raise ValueError("output_inits must not be empty")

    width = len(input_names)
    identity = tuple(range(width))
    original_outputs = dict(output_inits)
    if not enabled or width <= 1:
        return PermutedTruthTable(
            input_names=tuple(input_names),
            output_inits=original_outputs,
            canonical_output_inits=original_outputs,
            permutation=identity,
            enabled=enabled,
        )

    output_names = tuple(sorted(output_inits))
    best_outputs = original_outputs
    best_signature = tuple(best_outputs[name] for name in output_names)
    best_permutation = identity
    for permutation in permutations(range(width)):
        permuted_outputs = {
            name: permute_truth_init(init, width, tuple(permutation))
            for name, init in output_inits.items()
        }
        signature = tuple(permuted_outputs[name] for name in output_names)
        if signature < best_signature:
            best_outputs = permuted_outputs
            best_signature = signature
            best_permutation = tuple(permutation)

    return PermutedTruthTable(
        input_names=tuple(input_names),
        output_inits=original_outputs,
        canonical_output_inits=best_outputs,
        permutation=best_permutation,
        enabled=enabled,
    )


def permute_truth_init(init: int, width: int, permutation: tuple[int, ...]) -> int:
    """Permute input variables in a LSB-first truth-table INIT.

    ``permutation[i]`` is the original input index used by canonical input
    index ``i``.

    Parameters
    ----------
    init : int
        Original LSB-first INIT.
    width : int
        Number of inputs in the truth table.
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


def remap_permuted_solve_result(
    result: CutSolveResult,
    truth_table: PermutedTruthTable,
) -> CutSolveResult:
    """Remap a canonical SAT solution to the original input order.

    Parameters
    ----------
    result : CutSolveResult
        SAT result for ``truth_table.canonical_output_inits``.
    truth_table : PermutedTruthTable
        Canonical truth-table data used for the solve.

    Returns
    -------
    CutSolveResult
        Result with input mappings rewritten to original input names.
    """
    identity = tuple(range(len(truth_table.input_names)))
    if not result.sat or truth_table.permutation == identity:
        return result

    remap = {
        truth_table.input_names[canonical_index]: truth_table.input_names[
            original_index
        ]
        for canonical_index, original_index in enumerate(truth_table.permutation)
    }
    return replace(
        result,
        input_mapping={
            key: _remap_source_name(value, remap)
            for key, value in result.input_mapping.items()
        },
        scoped_input_mapping={
            key: _remap_source_name(value, remap)
            for key, value in result.scoped_input_mapping.items()
        },
    )


def _remap_source_name(source: str, remap: dict[str, str]) -> str:
    """Remap one source input name through a canonical input map.

    Parameters
    ----------
    source : str
        Original source name, possibly with a prefix.
    remap : dict[str, str]
        Mapping from canonical input name to original input name.

    Returns
    -------
    str
        Remapped source name with the same prefix.
    """
    prefix, separator, leaf = source.rpartition("/")
    name = leaf if separator else source
    remapped = remap.get(name)
    if remapped is None:
        return source
    return f"{prefix}/{remapped}" if separator else remapped
