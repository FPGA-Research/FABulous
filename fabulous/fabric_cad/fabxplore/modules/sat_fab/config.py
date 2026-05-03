"""Configuration key and policy objects.

This module describes which circuit configuration bits are fixed and which are left
symbolic for SAT synthesis.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from typing import TYPE_CHECKING

from fabulous.fabric_cad.fabxplore.modules.sat_fab.constants import ConfigKind

if TYPE_CHECKING:
    from fabulous.fabric_cad.fabxplore.modules.sat_fab.circuit import Circuit


class ConfigMode(StrEnum):
    """Configuration mode marker.

    Attributes
    ----------
    FIXED:
        The configuration bit is forced to a concrete value.
    SYMBOLIC:
        The SAT solver may choose the configuration bit.
    """

    FIXED = "fixed"
    SYMBOLIC = "symbolic"


@dataclass(frozen=True, order=True)
class ConfigKey:
    """Stable identifier for one configuration bit.

    Attributes
    ----------
    role : str
        Circuit role in an equivalence problem, normally ``"c1"`` or ``"c2"``.
    kind : ConfigKind
        Configuration family, such as ``"LUT"``, ``"ROUTE"``, or ``"INPUT"``.
    inst : str
        Instance or external configuration input name.
    index : int
        Bit index inside the configuration family.
    """

    role: str
    kind: ConfigKind
    inst: str
    index: int = 0


@dataclass
class ConfigSpec:
    """Fixed and symbolic configuration specification.

    Attributes
    ----------
    fixed : dict[ConfigKey, bool]
        Mapping from configuration keys to fixed Boolean values.
    symbolic : set[ConfigKey]
        Set of configuration keys the SAT solver may choose.
    """

    fixed: dict[ConfigKey, bool] = field(default_factory=dict)
    symbolic: set[ConfigKey] = field(default_factory=set)

    @staticmethod
    def empty() -> ConfigSpec:
        """Create an empty configuration specification.

        Returns
        -------
        ConfigSpec
            Specification with no fixed or symbolic bits.
        """
        return ConfigSpec()

    @staticmethod
    def fixed_lut(role: str, inst: str, k: int, init: int) -> ConfigSpec:
        """Create a fixed LUT INIT specification.

        Parameters
        ----------
        role : str
            Circuit role that owns the LUT.
        inst : str
            LUT instance name.
        k : int
            Number of LUT address inputs.
        init : int
            LSB-first INIT integer.

        Returns
        -------
        ConfigSpec
            Specification fixing all LUT INIT bits.
        """
        fixed = {
            ConfigKey(role, ConfigKind.LUT, inst, index): bool((init >> index) & 1)
            for index in range(1 << k)
        }
        return ConfigSpec(fixed=fixed)

    @staticmethod
    def fixed_inputs(role: str, values: dict[str, bool | int]) -> ConfigSpec:
        """Create fixed external configuration input constraints.

        Parameters
        ----------
        role : str
            Circuit role that owns the external config inputs.
        values : dict[str, bool | int]
            Mapping from config input name to Boolean-like value.

        Returns
        -------
        ConfigSpec
            Specification fixing the named external configuration inputs.
        """
        return ConfigSpec(
            fixed={
                ConfigKey(role, ConfigKind.INPUT, name, 0): bool(value)
                for name, value in values.items()
            }
        )

    @staticmethod
    def symbolic_all(circuit: Circuit, role: str) -> ConfigSpec:
        """Create a symbolic specification for all config bits in a circuit.

        Parameters
        ----------
        circuit : Circuit
            Circuit whose configuration bits should become symbolic.
        role : str
            Circuit role used to scope the keys.

        Returns
        -------
        ConfigSpec
            Specification marking all circuit configuration keys symbolic.
        """
        return ConfigSpec(symbolic=set(circuit.config_keys(role)))

    def merge(self, other: ConfigSpec) -> ConfigSpec:
        """Merge two configuration specifications.

        Parameters
        ----------
        other : ConfigSpec
            Specification to merge into this one.

        Returns
        -------
        ConfigSpec
            New merged specification.

        Raises
        ------
        ValueError
            If a key is fixed to conflicting values.
        """
        fixed = dict(self.fixed)
        for key, value in other.fixed.items():
            if key in fixed and fixed[key] != value:
                raise ValueError(f"conflicting fixed config value for {key}")
            fixed[key] = value
        symbolic = set(self.symbolic) | set(other.symbolic)
        symbolic.difference_update(fixed)
        return ConfigSpec(fixed=fixed, symbolic=symbolic)

    def fix(self, key: ConfigKey, value: bool | int) -> None:
        """Fix a single configuration bit.

        Parameters
        ----------
        key : ConfigKey
            Configuration key to constrain.
        value : bool | int
            Boolean-like value.
        """
        self.fixed[key] = bool(value)
        self.symbolic.discard(key)

    def mark_symbolic(self, key: ConfigKey) -> None:
        """Mark a single configuration bit symbolic.

        Parameters
        ----------
        key : ConfigKey
            Configuration key to expose to the SAT solver.
        """
        if key not in self.fixed:
            self.symbolic.add(key)

    def is_fixed(self, key: ConfigKey) -> bool:
        """Check whether a configuration bit is fixed.

        Parameters
        ----------
        key : ConfigKey
            Configuration key to query.

        Returns
        -------
        bool
            True when the key has a fixed value.
        """
        return key in self.fixed

    def is_symbolic(self, key: ConfigKey) -> bool:
        """Check whether a configuration bit is symbolic.

        Parameters
        ----------
        key : ConfigKey
            Configuration key to query.

        Returns
        -------
        bool
            True when the key is solver-controlled.
        """
        return key in self.symbolic
