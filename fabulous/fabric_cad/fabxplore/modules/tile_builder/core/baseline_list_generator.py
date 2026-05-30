"""Generate minimal FABulous switch-matrix list files for new tiles.

The tile builder creates a conservative, valid first matrix.  Rich routing patterns
belong in later graph-level optimizer passes.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from typing import TYPE_CHECKING

from fabulous.fabric_cad.fabxplore.modules.tile_builder.core.models import (
    BaselineListResult,
    BaselineRouting,
    FabulousCsvKeyword,
    FabulousSpecialFeature,
    TileBuilderGeneratedWire,
)
from fabulous.fabric_definition.define import IO

if TYPE_CHECKING:
    from fabulous.fabric_cad.fabxplore.modules.tile_builder.core.base_model import (
        BaseRoutingModel,
    )
    from fabulous.fabric_definition.bel import Bel


@dataclass
class _PairStats:
    """Collect statistics from one generated candidate list.

    Attributes
    ----------
    input_muxes : int
        Number of ordinary BEL input rows generated.
    output_muxes : int
        Number of base output rows generated.
    direct_connections : int
        Number of direct special connections.
    """

    input_muxes: int
    output_muxes: int
    direct_connections: int


def generate_baseline_list(
    tile_name: str,
    bels: list[Bel],
    routing: BaselineRouting,
    base_model: BaseRoutingModel,
    matrix_config_budget: int | None,
) -> BaselineListResult:
    """Generate a small switch-matrix list for one tile.

    Parameters
    ----------
    tile_name : str
        Name of the generated tile.
    bels : list[Bel]
        Parsed BEL instances in tile order.
    routing : BaselineRouting
        Baseline routing options.
    base_model : BaseRoutingModel
        Discovered base routing resources.
    matrix_config_budget : int | None
        Optional maximum allowed switch-matrix config bits.

    Returns
    -------
    BaselineListResult
        Generated list text and summary statistics.
    """
    best: BaselineListResult | None = None
    warnings: list[str] = []

    for input_fanin, output_fanin in _fanin_candidates(routing):
        pairs, stats = _generate_pairs(
            bels=bels,
            routing=routing,
            base_model=base_model,
            input_fanin=input_fanin,
            output_fanin=output_fanin,
        )
        matrix_bits = _estimate_config_bits([*base_model.existing_pairs, *pairs])
        result = BaselineListResult(
            text=_render_list(
                tile_name=tile_name,
                base_list_includes=base_model.list_includes,
                pairs=pairs,
                input_fanin=input_fanin,
                output_fanin=output_fanin,
            ),
            matrix_config_bits=matrix_bits,
            input_muxes=stats.input_muxes,
            output_muxes=stats.output_muxes,
            direct_connections=stats.direct_connections,
            input_fanin_used=input_fanin,
            output_fanin_used=output_fanin,
        )
        best = result
        if matrix_config_budget is None or matrix_bits <= matrix_config_budget:
            if (input_fanin, output_fanin) != (
                routing.input_fanin,
                routing.output_fanin,
            ):
                warnings.append(
                    "Reduced routing options to fit the matrix config-bit budget: "
                    f"input_fanin={input_fanin}, output_fanin={output_fanin}."
                )
                return result.model_copy(update={"warnings": tuple(warnings)})
            return result

    if best is None:
        return BaselineListResult(
            text=_render_list(
                tile_name=tile_name,
                base_list_includes=base_model.list_includes,
                pairs=[],
                input_fanin=routing.min_input_fanin,
                output_fanin=routing.min_output_fanin,
            ),
            matrix_config_bits=_estimate_config_bits(base_model.existing_pairs),
            input_muxes=0,
            output_muxes=0,
            direct_connections=0,
            input_fanin_used=routing.min_input_fanin,
            output_fanin_used=routing.min_output_fanin,
        )

    if matrix_config_budget is not None:
        warnings.append(
            "Baseline routing exceeds the matrix config-bit budget even at minimum "
            f"fanin: used={best.matrix_config_bits}, budget={matrix_config_budget}."
        )
    return best.model_copy(update={"warnings": tuple(warnings)})


def _fanin_candidates(routing: BaselineRouting) -> list[tuple[int, int]]:
    """Return fanin candidates from preferred to minimum.

    Parameters
    ----------
    routing : BaselineRouting
        Baseline routing options.

    Returns
    -------
    list[tuple[int, int]]
        Candidate ``(input_fanin, output_fanin)`` settings.
    """
    candidates: list[tuple[int, int]] = []
    for output_fanin in _descending_range(
        routing.output_fanin,
        routing.min_output_fanin,
    ):
        candidates.append((routing.input_fanin, output_fanin))
    for input_fanin in _descending_range(
        routing.input_fanin - 1,
        routing.min_input_fanin,
    ):
        for output_fanin in _descending_range(
            routing.output_fanin,
            routing.min_output_fanin,
        ):
            candidates.append((input_fanin, output_fanin))
    return list(dict.fromkeys(candidates))


def _descending_range(start: int, stop: int) -> range:
    """Return an inclusive descending range.

    Parameters
    ----------
    start : int
        First value.
    stop : int
        Last value.

    Returns
    -------
    range
        Inclusive descending range from ``start`` to ``stop``.
    """
    return range(start, stop - 1, -1)


def _generate_pairs(
    bels: list[Bel],
    routing: BaselineRouting,
    base_model: BaseRoutingModel,
    input_fanin: int,
    output_fanin: int,
) -> tuple[list[tuple[str, str]], _PairStats]:
    """Generate baseline list pairs for ordinary and special BEL wiring.

    Parameters
    ----------
    bels : list[Bel]
        Parsed BEL instances.
    routing : BaselineRouting
        Baseline routing options.
    base_model : BaseRoutingModel
        Discovered base routing resources.
    input_fanin : int
        Input fanin for ordinary BEL inputs.
    output_fanin : int
        Output fanin for base output rows.

    Returns
    -------
    tuple[list[tuple[str, str]], _PairStats]
        Generated list pairs and statistics.

    Raises
    ------
    ValueError
        If ordinary BEL input muxes are required but no routing sources exist.
    """
    pairs: list[tuple[str, str]] = []
    input_muxes = 0
    output_muxes = 0
    direct_connections = 0

    output_ports = [port for bel in bels for port in _ordinary_outputs(bel)]
    input_source_pool = _input_source_pool(base_model, output_ports, routing)
    output_source_pool = _output_source_pool(base_model)
    ordinary_input_count = sum(len(_ordinary_inputs(bel)) for bel in bels)
    if ordinary_input_count and not input_source_pool:
        raise ValueError("cannot build BEL input muxes without any routing sources")

    for bel_index, bel in enumerate(bels):
        for input_index, port in enumerate(_ordinary_inputs(bel)):
            sources = _rotated_take(
                input_source_pool,
                count=input_fanin,
                seed=_stable_index(f"{bel_index}:{input_index}:{port}"),
            )
            pairs.extend((port, source) for source in sources)
            if sources:
                input_muxes += 1

    output_rows = _output_rows(base_model, routing)
    if output_rows and not output_ports and not output_source_pool:
        raise ValueError("cannot cover base output rows without any routing sources")
    for output_index, destination in enumerate(output_rows):
        sources = _output_sources_for_row(
            output_index=output_index,
            output_ports=output_ports,
            output_source_pool=output_source_pool,
            output_fanin=output_fanin,
        )
        pairs.extend((destination, source) for source in sources)
        if sources:
            output_muxes += 1

    carry_pairs = _carry_pairs(bels)
    pairs.extend(carry_pairs)
    direct_connections += len(carry_pairs)

    shared_pairs = _local_shared_pairs(bels, base_model, input_source_pool, input_fanin)
    pairs.extend(shared_pairs)
    direct_connections += len(shared_pairs)

    return pairs, _PairStats(
        input_muxes=input_muxes,
        output_muxes=output_muxes,
        direct_connections=direct_connections,
    )


def _ordinary_inputs(bel: Bel) -> list[str]:
    """Return BEL inputs that should use ordinary routing.

    Parameters
    ----------
    bel : Bel
        Parsed BEL instance.

    Returns
    -------
    list[str]
        Ordinary routable input port names.
    """
    special = _carry_ports(bel) | _local_shared_ports(bel)
    return [port for port in bel.inputs if port not in special]


def _ordinary_outputs(bel: Bel) -> list[str]:
    """Return BEL outputs that should use ordinary routing.

    Parameters
    ----------
    bel : Bel
        Parsed BEL instance.

    Returns
    -------
    list[str]
        Ordinary routable output port names.
    """
    special = _carry_ports(bel) | _local_shared_ports(bel)
    return [port for port in bel.outputs if port not in special]


def _carry_ports(bel: Bel) -> set[str]:
    """Return carry ports declared by one BEL.

    Parameters
    ----------
    bel : Bel
        Parsed BEL instance.

    Returns
    -------
    set[str]
        Carry input and output ports.
    """
    ports: set[str] = set()
    for carry in bel.carry.values():
        ports.update(carry.values())
    return ports


def _local_shared_ports(bel: Bel) -> set[str]:
    """Return local shared ports declared by one BEL.

    Parameters
    ----------
    bel : Bel
        Parsed BEL instance.

    Returns
    -------
    set[str]
        Local shared port names.
    """
    return {port for port, _direction in bel.localShared.values()}


def _input_source_pool(
    base_model: BaseRoutingModel,
    output_ports: list[str],
    routing: BaselineRouting,
) -> list[str]:
    """Return generic sources available to ordinary BEL input muxes.

    Parameters
    ----------
    base_model : BaseRoutingModel
        Discovered base routing resources.
    output_ports : list[str]
        Ordinary BEL outputs.
    routing : BaselineRouting
        Baseline routing options.

    Returns
    -------
    list[str]
        Source names.
    """
    sources: list[str] = []
    if routing.derive_sources_from_base:
        sources.extend(base_model.input_ports)
    if routing.allow_bel_output_feedback_sources:
        sources.extend(output_ports)
    return _unique(sources)


def _output_source_pool(base_model: BaseRoutingModel) -> list[str]:
    """Return route-through sources available to base output rows.

    Parameters
    ----------
    base_model : BaseRoutingModel
        Discovered base routing resources.

    Returns
    -------
    list[str]
        Source names.
    """
    return _unique(base_model.input_ports)


def _output_rows(base_model: BaseRoutingModel, routing: BaselineRouting) -> list[str]:
    """Return output rows to drive from ordinary BEL outputs.

    Parameters
    ----------
    base_model : BaseRoutingModel
        Discovered base routing resources.
    routing : BaselineRouting
        Baseline routing options.

    Returns
    -------
    list[str]
        Output row names.
    """
    if routing.cover_unconnected_outputs:
        return base_model.uncovered_outputs
    return base_model.output_ports


def _output_sources_for_row(
    output_index: int,
    output_ports: list[str],
    output_source_pool: list[str],
    output_fanin: int,
) -> list[str]:
    """Return sources for one discovered output row.

    Parameters
    ----------
    output_index : int
        Zero-based output row index.
    output_ports : list[str]
        Ordinary BEL outputs.
    output_source_pool : list[str]
        Route-through input sources.
    output_fanin : int
        Desired output row fanin.

    Returns
    -------
    list[str]
        Sources for the row.
    """
    sources: list[str] = []
    if output_ports:
        sources.append(output_ports[output_index % len(output_ports)])
    sources.extend(
        _rotated_take(
            output_source_pool,
            count=max(0, output_fanin - len(sources)),
            seed=output_index,
        )
    )
    return _unique_take(sources, output_fanin)


def _stable_index(value: str) -> int:
    """Return a stable small hash for deterministic source spreading.

    Parameters
    ----------
    value : str
        String to hash.

    Returns
    -------
    int
        Deterministic integer hash.
    """
    return sum(ord(char) for char in value)


def _carry_pairs(bels: list[Bel]) -> list[tuple[str, str]]:
    """Return direct carry-chain list pairs for all carry prefixes.

    Parameters
    ----------
    bels : list[Bel]
        Parsed BEL instances.

    Returns
    -------
    list[tuple[str, str]]
        Direct carry-chain pairs.
    """
    by_prefix: dict[str, dict[IO, list[str]]] = defaultdict(
        lambda: {IO.INPUT: [], IO.OUTPUT: []}
    )
    for bel in bels:
        for prefix, carry in bel.carry.items():
            if IO.INPUT in carry:
                by_prefix[prefix][IO.INPUT].append(carry[IO.INPUT])
            if IO.OUTPUT in carry:
                by_prefix[prefix][IO.OUTPUT].append(carry[IO.OUTPUT])

    pairs: list[tuple[str, str]] = []
    for index, prefix in enumerate(sorted(by_prefix)):
        inputs = by_prefix[prefix][IO.INPUT]
        outputs = by_prefix[prefix][IO.OUTPUT]
        if not inputs or not outputs:
            continue
        chain_sources = [
            _carry_boundary(TileBuilderGeneratedWire.CARRY_IN, index),
            *outputs,
        ]
        chain_sinks = [
            *inputs,
            _carry_boundary(TileBuilderGeneratedWire.CARRY_OUT, index),
        ]
        pairs.extend(zip(chain_sinks, chain_sources, strict=False))
    return pairs


def _carry_boundary(port: TileBuilderGeneratedWire, index: int) -> str:
    """Return the switch-matrix name for a one-bit tile carry port.

    Parameters
    ----------
    port : TileBuilderGeneratedWire
        Tile carry port base name, usually ``Ci`` or ``Co``.
    index : int
        Carry-chain index from the tile CSV.

    Returns
    -------
    str
        Expanded switch-matrix port name.
    """
    return f"{port}{index}0"


def _local_shared_pairs(
    bels: list[Bel],
    base_model: BaseRoutingModel,
    input_source_pool: list[str],
    fanin: int,
) -> list[tuple[str, str]]:
    """Return direct local shared reset and enable list pairs.

    Parameters
    ----------
    bels : list[Bel]
        Parsed BEL instances.
    base_model : BaseRoutingModel
        Discovered base routing resources.
    input_source_pool : list[str]
        Sources available for shared jump begin rows.
    fanin : int
        Number of routeable sources for the shared jump begin port.

    Returns
    -------
    list[tuple[str, str]]
        Direct local shared pairs.
    """
    pairs: list[tuple[str, str]] = []
    shared_specs = {
        FabulousSpecialFeature.RESET: (
            f"{TileBuilderGeneratedWire.RESET_BEGIN}0",
            f"{TileBuilderGeneratedWire.RESET_END}0",
            base_model.gnd_source,
        ),
        FabulousSpecialFeature.ENABLE: (
            f"{TileBuilderGeneratedWire.ENABLE_BEGIN}0",
            f"{TileBuilderGeneratedWire.ENABLE_END}0",
            base_model.vcc_source,
        ),
    }
    for shared_kind, (begin, end, neutral) in shared_specs.items():
        shared_ports = [
            bel.localShared[shared_kind][0]
            for bel in bels
            if shared_kind in bel.localShared
        ]
        if not shared_ports:
            continue
        pairs.extend(
            (begin, source)
            for source in _rotated_take(
                input_source_pool,
                count=fanin,
                seed=_stable_index(shared_kind),
            )
        )
        pairs.extend((port, end) for port in shared_ports)
        if neutral is not None:
            pairs.extend((port, neutral) for port in shared_ports)
    return pairs


def _render_list(
    tile_name: str,
    base_list_includes: list[str],
    pairs: list[tuple[str, str]],
    input_fanin: int,
    output_fanin: int,
) -> str:
    """Render list-file text from connection pairs.

    Parameters
    ----------
    tile_name : str
        Name of the generated tile.
    base_list_includes : list[str]
        Include paths for FABulous base lists.
    pairs : list[tuple[str, str]]
        Generated list pairs.
    input_fanin : int
        Input fanin used for the generated list.
    output_fanin : int
        Output fanin used for the generated list.

    Returns
    -------
    str
        Complete list-file text.
    """
    grouped: dict[str, list[str]] = defaultdict(list)
    for source, sink in pairs:
        if sink not in grouped[source]:
            grouped[source].append(sink)

    lines = [
        f"# {tile_name} baseline switch matrix list",
        "# Generated by fabxplore tile_builder.",
        f"# input_fanin={input_fanin}, output_fanin={output_fanin}",
    ]
    lines.extend(
        f"{FabulousCsvKeyword.INCLUDE}, {include}" for include in base_list_includes
    )
    lines.append("")
    for source, sinks in grouped.items():
        if len(sinks) == 1:
            lines.append(f"{source},{sinks[0]}")
        else:
            joined = "|".join(sinks)
            lines.append(f"{{{len(sinks)}}}{source},[{joined}]")
    return "\n".join(lines) + "\n"


def _estimate_config_bits(pairs: list[tuple[str, str]]) -> int:
    """Estimate switch-matrix configuration bits from list pairs.

    Parameters
    ----------
    pairs : list[tuple[str, str]]
        List pairs after include expansion.

    Returns
    -------
    int
        Estimated configuration bits.
    """
    grouped: dict[str, list[str]] = defaultdict(list)
    for source, sink in pairs:
        if sink not in grouped[source]:
            grouped[source].append(sink)
    return sum((len(sinks) - 1).bit_length() for sinks in grouped.values())


def _unique_take(values: list[str], count: int) -> list[str]:
    """Return up to ``count`` unique entries while preserving order.

    Parameters
    ----------
    values : list[str]
        Candidate values.
    count : int
        Maximum number of entries to return.

    Returns
    -------
    list[str]
        Unique prefix of ``values``.
    """
    result: list[str] = []
    for value in values:
        if value not in result:
            result.append(value)
        if len(result) >= count:
            break
    return result


def _rotated_take(values: list[str], count: int, seed: int) -> list[str]:
    """Return up to ``count`` unique values from a rotated source list.

    Parameters
    ----------
    values : list[str]
        Candidate values.
    count : int
        Maximum number of entries.
    seed : int
        Rotation seed.

    Returns
    -------
    list[str]
        Selected values.
    """
    if not values or count <= 0:
        return []
    offset = seed % len(values)
    rotated = [*values[offset:], *values[:offset]]
    return _unique_take(rotated, count)


def _unique(values: list[str]) -> list[str]:
    """Return unique strings while preserving order.

    Parameters
    ----------
    values : list[str]
        Values to deduplicate.

    Returns
    -------
    list[str]
        Unique values.
    """
    return list(dict.fromkeys(values))
