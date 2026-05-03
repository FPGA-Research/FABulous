"""Fast truth-table circuit specifications.

This module provides the LUT fast path used when a target circuit is best represented
directly by one or more truth-table INIT values.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Callable


@dataclass
class TruthTableSpec:
    """Fast fixed truth-table circuit.

    Attributes
    ----------
    name : str
        Human-readable circuit name.
    inputs : list[str]
        Ordered input names. Input zero is the least significant INIT index bit.
    outputs : dict[str, int]
        Mapping from output name to LSB-first truth-table INIT integer.
    reduce_lut_symmetry : bool
        Whether CEGIS may canonicalize examples using symmetric input pins.
    """

    name: str
    inputs: list[str]
    outputs: dict[str, int]
    reduce_lut_symmetry: bool = True

    def input_names(self) -> list[str]:
        """Return ordered input names.

        Returns
        -------
        list[str]
            Ordered input names.
        """
        return self.inputs[:]

    def output_names(self) -> list[str]:
        """Return ordered output names.

        Returns
        -------
        list[str]
            Output names in insertion order.
        """
        return list(self.outputs.keys())

    def n_inputs(self) -> int:
        """Return the number of truth-table inputs.

        Returns
        -------
        int
            Number of input variables.
        """
        return len(self.inputs)

    def eval_concrete(self, values: dict[str, bool]) -> dict[str, bool]:
        """Evaluate the truth table for one concrete input assignment.

        Parameters
        ----------
        values : dict[str, bool]
            Mapping from input name to Boolean value.

        Returns
        -------
        dict[str, bool]
            Output values for the assignment.
        """
        index = 0
        for bit_index, name in enumerate(self.inputs):
            if values[name]:
                index |= 1 << bit_index
        return {
            out_name: bool((init >> index) & 1)
            for out_name, init in self.outputs.items()
        }

    def symmetric_groups(self) -> list[list[str]]:
        """Compute groups of pairwise symmetric input pins.

        Returns
        -------
        list[list[str]]
            Input-name groups whose members can be swapped without changing all
            outputs.
        """
        parent = list(range(len(self.inputs)))

        def find(index: int) -> int:
            while parent[index] != index:
                parent[index] = parent[parent[index]]
                index = parent[index]
            return index

        def union(left: int, right: int) -> None:
            root_left = find(left)
            root_right = find(right)
            if root_left != root_right:
                parent[root_right] = root_left

        for left in range(len(self.inputs)):
            for right in range(left + 1, len(self.inputs)):
                if self.are_inputs_symmetric(left, right):
                    union(left, right)

        groups_by_root: dict[int, list[str]] = {}
        for index, name in enumerate(self.inputs):
            groups_by_root.setdefault(find(index), []).append(name)
        return [group for group in groups_by_root.values() if len(group) > 1]

    def are_inputs_symmetric(self, left: int, right: int) -> bool:
        """Check whether two input pins are truth-table symmetric.

        Parameters
        ----------
        left : int
            First input index.
        right : int
            Second input index.

        Returns
        -------
        bool
            True when swapping the two inputs preserves every output.
        """
        if left == right:
            return True
        for index in range(1 << len(self.inputs)):
            swapped = _swap_index_bits(index, left, right)
            for init in self.outputs.values():
                if ((init >> index) & 1) != ((init >> swapped) & 1):
                    return False
        return True

    def canonical_example(
        self,
        values: dict[str, bool],
    ) -> tuple[tuple[str, bool], ...]:
        """Canonicalize an input assignment using symmetric input groups.

        Parameters
        ----------
        values : dict[str, bool]
            Concrete input assignment.

        Returns
        -------
        tuple[tuple[str, bool], ...]
            Stable canonical assignment key.
        """
        if not self.reduce_lut_symmetry:
            return tuple((name, bool(values[name])) for name in self.inputs)
        canonical = {name: bool(values[name]) for name in self.inputs}
        for group in self.symmetric_groups():
            sorted_values = sorted((canonical[name] for name in group), reverse=True)
            for name, value in zip(group, sorted_values, strict=True):
                canonical[name] = value
        return tuple((name, canonical[name]) for name in self.inputs)


def init_from_function(
    inputs: list[str],
    function: Callable[[dict[str, bool]], bool],
) -> int:
    """Build a truth-table INIT integer from a Python function.

    Parameters
    ----------
    inputs : list[str]
        Ordered input names. Input zero is the least significant INIT index bit.
    function : Callable[[dict[str, bool]], bool]
        Callable receiving a ``dict[str, bool]`` and returning a Boolean-like
        output value.

    Returns
    -------
    int
        LSB-first INIT integer.
    """
    init = 0
    for index in range(1 << len(inputs)):
        values = {
            name: bool((index >> bit_index) & 1)
            for bit_index, name in enumerate(inputs)
        }
        if function(values):
            init |= 1 << index
    return init


def _swap_index_bits(index: int, left: int, right: int) -> int:
    """Swap two bit positions in an integer index.

    Parameters
    ----------
    index : int
        Original truth-table row index.
    left : int
        First bit position.
    right : int
        Second bit position.

    Returns
    -------
    int
        Index with the two bit positions swapped.
    """
    left_bit = (index >> left) & 1
    right_bit = (index >> right) & 1
    if left_bit == right_bit:
        return index
    return index ^ ((1 << left) | (1 << right))
