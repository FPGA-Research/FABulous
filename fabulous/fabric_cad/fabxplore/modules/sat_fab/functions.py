"""Boolean function helpers.

This module provides the ``Func`` expression API used to build truth-table
targets and fixed truth-table blocks without manually writing INIT values.
"""

from __future__ import annotations

from dataclasses import dataclass
from functools import reduce
from inspect import signature
from operator import and_, or_, xor
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Callable


@dataclass(frozen=True)
class Func:
    """Boolean function expression.

    Parameters
    ----------
    evaluator : Callable[[dict[str, bool]], bool]
        Callable that evaluates the expression from named Boolean values.

    Attributes
    ----------
    evaluator : Callable[[dict[str, bool]], bool]
        Callable that evaluates the expression from named Boolean values.
    """

    evaluator: Callable[[dict[str, bool]], bool]

    def eval(self, values: dict[str, bool]) -> bool:
        """Evaluate the function.

        Parameters
        ----------
        values : dict[str, bool]
            Mapping from input names to Boolean values.

        Returns
        -------
        bool
            Function result.
        """
        return bool(self.evaluator(values))

    @staticmethod
    def expr(function: Callable[..., bool]) -> Func:
        """Create a function from a Python callable.

        Parameters
        ----------
        function : Callable[..., bool]
            Callable whose parameter names are circuit input names.

        Returns
        -------
        Func
            Function expression.
        """
        names = list(signature(function).parameters)

        def evaluator(values: dict[str, bool]) -> bool:
            return bool(function(**{name: values[name] for name in names}))

        return Func(evaluator)

    @staticmethod
    def var(name: str) -> Func:
        """Create an input variable expression.

        Parameters
        ----------
        name : str
            Input name.

        Returns
        -------
        Func
            Variable expression.
        """
        return Func(lambda values: values[name])

    @staticmethod
    def const(value: bool) -> Func:
        """Create a constant expression.

        Parameters
        ----------
        value : bool
            Constant Boolean value.

        Returns
        -------
        Func
            Constant expression.
        """
        return Func(lambda _values: bool(value))

    @staticmethod
    def xor(*items: str | Func) -> Func:
        """Create an XOR reduction expression.

        Parameters
        ----------
        *items : str | Func
            Input names or function expressions.

        Returns
        -------
        Func
            XOR expression.
        """
        funcs = [_coerce_func(item) for item in items]
        return Func(
            lambda values: reduce(xor, (fn.eval(values) for fn in funcs), False)
        )

    @staticmethod
    def and_(*items: str | Func) -> Func:
        """Create an AND reduction expression.

        Parameters
        ----------
        *items : str | Func
            Input names or function expressions.

        Returns
        -------
        Func
            AND expression.
        """
        funcs = [_coerce_func(item) for item in items]
        return Func(
            lambda values: reduce(and_, (fn.eval(values) for fn in funcs), True)
        )

    @staticmethod
    def or_(*items: str | Func) -> Func:
        """Create an OR reduction expression.

        Parameters
        ----------
        *items : str | Func
            Input names or function expressions.

        Returns
        -------
        Func
            OR expression.
        """
        funcs = [_coerce_func(item) for item in items]
        return Func(
            lambda values: reduce(or_, (fn.eval(values) for fn in funcs), False)
        )

    @staticmethod
    def not_(item: str | Func) -> Func:
        """Create a NOT expression.

        Parameters
        ----------
        item : str | Func
            Input name or function expression.

        Returns
        -------
        Func
            NOT expression.
        """
        fn = _coerce_func(item)
        return Func(lambda values: not fn.eval(values))

    @staticmethod
    def mux(sel: str | Func, d1: str | Func, d0: str | Func) -> Func:
        """Create a two-input mux expression.

        Parameters
        ----------
        sel : str | Func
            Selector input name or expression.
        d1 : str | Func
            Data selected when ``sel`` is true.
        d0 : str | Func
            Data selected when ``sel`` is false.

        Returns
        -------
        Func
            Mux expression.
        """
        sel_fn = _coerce_func(sel)
        d1_fn = _coerce_func(d1)
        d0_fn = _coerce_func(d0)
        return Func(
            lambda values: (
                d1_fn.eval(values) if sel_fn.eval(values) else d0_fn.eval(values)
            )
        )

    @staticmethod
    def mux_indexed(data: list[str | Func], select: list[str | Func]) -> Func:
        """Create an indexed mux expression.

        Parameters
        ----------
        data : list[str | Func]
            Data inputs where index zero is selected by all-zero select bits.
        select : list[str | Func]
            LSB-first select inputs.

        Returns
        -------
        Func
            Indexed mux expression.
        """
        data_funcs = [_coerce_func(item) for item in data]
        select_funcs = [_coerce_func(item) for item in select]

        def evaluator(values: dict[str, bool]) -> bool:
            index = 0
            for bit_index, sel in enumerate(select_funcs):
                if sel.eval(values):
                    index |= 1 << bit_index
            return data_funcs[index].eval(values)

        return Func(evaluator)


def init_from_func(inputs: list[str], func: Func | Callable[..., bool]) -> int:
    """Build a truth-table INIT from a function expression.

    Parameters
    ----------
    inputs : list[str]
        Ordered input names.
    func : Func | Callable[..., bool]
        Function expression or callable.

    Returns
    -------
    int
        LSB-first INIT integer.
    """
    expr = func if isinstance(func, Func) else Func.expr(func)
    init = 0
    for index in range(1 << len(inputs)):
        values = {
            name: bool((index >> bit_index) & 1)
            for bit_index, name in enumerate(inputs)
        }
        if expr.eval(values):
            init |= 1 << index
    return init


def _coerce_func(item: str | Func | bool | int) -> Func:
    """Convert a supported object into a function expression.

    Parameters
    ----------
    item : str | Func | bool | int
        Input name, function expression, or Boolean constant.

    Returns
    -------
    Func
        Function expression.
    """
    if isinstance(item, Func):
        return item
    if isinstance(item, str):
        return Func.var(item)
    return Func.const(bool(item))
