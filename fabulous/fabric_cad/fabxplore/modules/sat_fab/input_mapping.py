"""Input and output routing specifications.

This module describes virtual crossbars that Equiv can place around a circuit without
mutating the circuit graph itself.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum


class InputSourceKind(StrEnum):
    """Input-routing source kinds.

    Attributes
    ----------
    INPUT:
        Source is a normal universally quantified input.
    CONST:
        Source is a Boolean constant.
    """

    INPUT = "INPUT"
    CONST = "CONST"


@dataclass(frozen=True)
class InputHandle:
    """One circuit-local input variable.

    Attributes
    ----------
    role : str
        Circuit role, normally ``"c1"`` or ``"c2"``.
    name : str
        Local input port name.
    """

    role: str
    name: str

    def display(self, separator: str = "/") -> str:
        """Return a scoped user-facing name.

        Parameters
        ----------
        separator : str
            Separator between role and local port name.

        Returns
        -------
        str
            Scoped input name.
        """
        return f"{self.role}{separator}{self.name}"


@dataclass(frozen=True)
class InputSource:
    """One source candidate for a routed circuit input.

    Attributes
    ----------
    kind : InputSourceKind
        Source kind.
    name : str
        User-facing source name.
    role : str | None
        Source circuit role for normal input sources.
    value : bool | None
        Constant value when ``kind`` is ``InputSourceKind.CONST``.
    """

    kind: InputSourceKind
    name: str
    role: str | None = None
    value: bool | None = None

    @staticmethod
    def input(name: str, role: str | None = None) -> InputSource:
        """Create a normal-input source.

        Parameters
        ----------
        name : str
            Normal input name.
        role : str | None
            Optional source circuit role.

        Returns
        -------
        InputSource
            Input source.
        """
        return InputSource(InputSourceKind.INPUT, name, role=role)

    @staticmethod
    def const(value: bool | int) -> InputSource:
        """Create a constant source.

        Parameters
        ----------
        value : bool | int
            Boolean-like constant value.

        Returns
        -------
        InputSource
            Constant source.
        """
        bool_value = bool(value)
        return InputSource(
            InputSourceKind.CONST,
            str(int(bool_value)),
            value=bool_value,
        )

    def display(self, scoped: bool = False, separator: str = "/") -> str:
        """Return a user-facing source name.

        Parameters
        ----------
        scoped : bool
            Whether normal input sources include their circuit role.
        separator : str
            Separator between role and local port name.

        Returns
        -------
        str
            Source display string.
        """
        if scoped and self.kind == InputSourceKind.INPUT and self.role is not None:
            return f"{self.role}{separator}{self.name}"
        return self.name


@dataclass(frozen=True)
class InputRoute:
    """One virtual route that drives a circuit input port.

    Attributes
    ----------
    port : str
        Circuit input port name.
    inst : str
        Configuration instance name for the route selector.
    sources : tuple[InputSource, ...]
        Candidate sources for this input port.
    """

    port: str
    inst: str
    sources: tuple[InputSource, ...]


@dataclass(frozen=True)
class InputRouteSpec:
    """Virtual input-routing specification for one circuit.

    Attributes
    ----------
    routes : tuple[InputRoute, ...]
        Routes that drive selected circuit input ports.
    allow_reuse : bool
        Whether multiple ports may select the same source.
    """

    routes: tuple[InputRoute, ...]
    allow_reuse: bool = True

    def routed_ports(self) -> set[str]:
        """Return the circuit input ports driven by virtual routes.

        Returns
        -------
        set[str]
            Routed input port names.
        """
        return {route.port for route in self.routes}

    def config_instances(self) -> list[str]:
        """Return route configuration instance names.

        Returns
        -------
        list[str]
            Route instance names.
        """
        return [route.inst for route in self.routes]


@dataclass(frozen=True)
class OutputRoute:
    """One virtual route that selects a circuit output.

    Attributes
    ----------
    target : str
        Opposite-side output name being matched.
    target_role : str
        Role that owns the target output.
    inst : str
        Configuration instance name for the route selector.
    sources : tuple[str, ...]
        Candidate output names from the routed circuit.
    """

    target: str
    target_role: str
    inst: str
    sources: tuple[str, ...]


@dataclass(frozen=True)
class OutputRouteSpec:
    """Virtual output-routing specification for one circuit.

    Attributes
    ----------
    routes : tuple[OutputRoute, ...]
        Routes that select output ports for comparison.
    allow_reuse : bool
        Whether multiple target outputs may select the same source output.
    """

    routes: tuple[OutputRoute, ...]
    allow_reuse: bool = True

    def target_outputs(self) -> set[str]:
        """Return opposite-side output names driven by virtual routes.

        Returns
        -------
        set[str]
            Target output names.
        """
        return {route.target for route in self.routes}

    def source_outputs(self) -> set[str]:
        """Return candidate source output names needed from the routed circuit.

        Returns
        -------
        set[str]
            Source output names.
        """
        return {source for route in self.routes for source in route.sources}

    def config_instances(self) -> list[str]:
        """Return route configuration instance names.

        Returns
        -------
        list[str]
            Route instance names.
        """
        return [route.inst for route in self.routes]
