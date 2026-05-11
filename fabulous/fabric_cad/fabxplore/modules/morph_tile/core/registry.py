"""Registry for morph-tile circuit adapters.

The registry converts public string options into typed enum values and instantiates
concrete circuit adapters. New cut kinds should be added here without changing the
mapper orchestration loop.
"""

from typing import Any

from fabulous.fabric_cad.fabxplore.modules.morph_tile.circuits.chain import (
    ChainCircuit,
    ChainCircuitOptions,
)
from fabulous.fabric_cad.fabxplore.modules.morph_tile.circuits.frac_lut import (
    FracLutCircuit,
    FracLutCircuitOptions,
)
from fabulous.fabric_cad.fabxplore.modules.morph_tile.circuits.lut import (
    LutCircuit,
    LutCircuitOptions,
)
from fabulous.fabric_cad.fabxplore.modules.morph_tile.core.base import (
    MorphCircuitAdapter,
    MorphCircuitEnvironment,
    MorphCircuitKind,
)


def build_morph_circuits(
    env: MorphCircuitEnvironment,
    enabled_circuits: list[str | MorphCircuitKind] | None,
) -> list[MorphCircuitAdapter[Any]]:
    """Instantiate circuit adapters requested by public pass options.

    Parameters
    ----------
    env : MorphCircuitEnvironment
        Shared runtime services and options for all adapters.
    enabled_circuits : list[str | MorphCircuitKind] | None
        Circuit kinds to enable. ``None`` enables only normal ``$lut`` support.

    Returns
    -------
    list[MorphCircuitAdapter[Any]]
        Instantiated adapters in requested order.

    Raises
    ------
    ValueError
        If an unknown circuit kind is requested.
    """
    kinds = _normalize_enabled_circuits(enabled_circuits)
    circuits: list[MorphCircuitAdapter[Any]] = []
    for kind in kinds:
        if kind is MorphCircuitKind.LUT:
            circuits.append(
                LutCircuit(
                    env=env,
                    options=LutCircuitOptions.model_validate(
                        _circuit_options(env, kind)
                    ),
                )
            )
            continue
        if kind is MorphCircuitKind.FRAC_LUT:
            circuits.append(
                FracLutCircuit(
                    env=env,
                    options=FracLutCircuitOptions.model_validate(
                        _circuit_options(env, kind)
                    ),
                )
            )
            continue
        if kind is MorphCircuitKind.CHAIN:
            circuits.append(
                ChainCircuit(
                    env=env,
                    options=ChainCircuitOptions.model_validate(
                        _circuit_options(env, kind)
                    ),
                )
            )
            continue
        raise ValueError(f"Unsupported morph circuit kind: {kind}")
    return circuits


def _normalize_enabled_circuits(
    enabled_circuits: list[str | MorphCircuitKind] | None,
) -> list[MorphCircuitKind]:
    """Normalize public circuit-kind values to ``MorphCircuitKind``.

    Parameters
    ----------
    enabled_circuits : list[str | MorphCircuitKind] | None
        Public option values.

    Returns
    -------
    list[MorphCircuitKind]
        Normalized circuit kinds.
    """
    values = enabled_circuits or [MorphCircuitKind.LUT]
    return [
        value if isinstance(value, MorphCircuitKind) else MorphCircuitKind(value)
        for value in values
    ]


def _circuit_options(
    env: MorphCircuitEnvironment,
    kind: MorphCircuitKind,
) -> dict[str, object]:
    """Return one adapter option dictionary from the environment.

    Parameters
    ----------
    env : MorphCircuitEnvironment
        Shared adapter environment.
    kind : MorphCircuitKind
        Circuit adapter kind.

    Returns
    -------
    dict[str, object]
        Flat option payload for ``kind``.
    """
    options = env.options.get("circuit_options")
    if not isinstance(options, dict):
        return {}
    circuit_options = options.get(kind.value, {})
    return circuit_options if isinstance(circuit_options, dict) else {}
