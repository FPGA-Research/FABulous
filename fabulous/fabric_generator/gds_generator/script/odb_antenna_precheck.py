"""OpenDB script predicting fabric-level antenna violations from one routed tile.

A FABulous routing wire declared with an offset of N becomes a single conductor N
tiles long once the fabric is stitched, because the `my_buf` pass-through buffers
are `assign X = A` and do not survive synthesis. The tile flow only ever measures
one tile's worth of that conductor, so the violation appears after stitching, when
fixing it means rebuilding tiles.

Rather than re-measuring the geometry, this asks OpenROAD's own antenna checker
the question with a scaled limit. `AntennaChecker::getAntennaViolations` takes a
`ratio_margin` percentage that multiplies every required ratio by `1 - margin/100`,
and holding a net to `limit / span` is arithmetically identical to giving it
`span` times the metal. So a margin of `100 * (1 - 1/span)` asks "would this net
violate if it were N tiles long", and the `excess_ratio` that comes back is the
predicted stitched headroom directly.

Doing it this way means the PDK's real rules apply -- side-area versus plan-area
ratios, PWL curves against diffusion area, cumulative ratios and the diodes
already placed -- instead of an approximation of them.
"""

import json
import re
from pathlib import Path
from typing import Any

import click
from librelane.logging.logger import info, warn
from librelane.scripts.odbpy.reader import click_odb

# The FABulous package is not importable from the OpenROAD interpreter, so the
# bus-index rule is restated here rather than shared with the step that calls it.
_BUS_INDEX = re.compile(r"(\[\d+\]|\d+)$")


def base_name(net_name: str) -> str:
    """Strip a bus index and any escaping from a net name.

    Parameters
    ----------
    net_name : str
        Net name as it appears in the database, e.g. `FrameData[12]`.

    Returns
    -------
    str
        The bare signal name, e.g. `FrameData`.
    """
    return _BUS_INDEX.sub("", net_name.split("/")[-1].lstrip("\\"))


def margin_for_span(span: int) -> float:
    """Return the ratio margin that holds a net to `limit / span`.

    OpenROAD scales every required ratio by `1 - margin/100`, so this is the
    margin at which a net is judged as though it carried `span` tiles of metal.

    Parameters
    ----------
    span : int
        How many tiles the wire runs across. Must be at least 1.

    Returns
    -------
    float
        Ratio margin as a percentage. A float rather than a `Decimal` because
        it is handed straight to OpenROAD, whose binding takes a C++ double.

    Raises
    ------
    ValueError
        If `span` is less than 1.
    """
    if span < 1:
        raise ValueError(f"span must be at least 1, got {span}")
    return 100.0 * (1.0 - 1.0 / span)


def nets_to_check(block: Any, spans: dict[str, int]) -> list[tuple[Any, int]]:  # noqa: ANN401
    """Pair each net in the block with the span its declared wire travels.

    A wire is matched either by its full net name or by its bus base name, so a
    single declared `FrameData` covers every `FrameData[n]`.

    Parameters
    ----------
    block : Any
        The `odb.dbBlock` being checked.
    spans : dict[str, int]
        Span in tiles, keyed by declared wire name.

    Returns
    -------
    list[tuple[Any, int]]
        Nets that travel more than one tile, with their span, name-ordered.
        Nets that stay inside the tile are left out: at span 1 this predicts
        nothing that `OpenROAD.CheckAntennas` has not already reported.
    """
    matched: list[tuple[Any, int]] = []
    for net in block.getNets():
        name = net.getName()
        span = spans.get(name, spans.get(base_name(name)))
        if span is not None and span > 1:
            matched.append((net, int(span)))
    matched.sort(key=lambda pair: pair[0].getName())
    return matched


def gate_pins(net: Any) -> list[str]:  # noqa: ANN401
    """Return the `instance/pin` sinks on a net that a diode would protect.

    Parameters
    ----------
    net : Any
        The `odb.dbNet` to inspect.

    Returns
    -------
    list[str]
        Sink names in the form `Odb.InsertECODiodes` expects. Only pins the LEF
        gives a gate area are included, which excludes any diode already on the
        net -- a diode declares diffusion area, not gate area.
    """
    pins = []
    for iterm in net.getITerms():
        if iterm.getIoType() != "INPUT":
            continue
        mterm = iterm.getMTerm()
        if not mterm.hasDefaultAntennaModel():
            continue
        pins.append(f"{iterm.getInst().getName()}/{mterm.getName()}")
    return pins


def routing_level_names(tech: Any) -> dict[int, str]:  # noqa: ANN401
    """Map each routing level to its layer name.

    Parameters
    ----------
    tech : Any
        The `odb.dbTech` of the design.

    Returns
    -------
    dict[int, str]
        Layer name keyed by routing level, as reported on a violation.
    """
    return {
        layer.getRoutingLevel(): layer.getName()
        for layer in tech.getLayers()
        if layer.getType() == "ROUTING"
    }


def predict(reader: Any, spans: dict[str, int]) -> list[dict[str, Any]]:  # noqa: ANN401
    """Ask OpenROAD which wires would violate once the fabric is stitched.

    Parameters
    ----------
    reader : Any
        The ODB reader supplied by `click_odb`.
    spans : dict[str, int]
        Span in tiles, keyed by declared wire name.

    Returns
    -------
    list[dict[str, Any]]
        One record per predicted violation, worst headroom first.
    """
    block = reader.block
    checker = reader.design.getAntennaChecker()
    checker.initAntennaRules()

    # Post-global-route the block carries guides rather than wires. OpenROAD's
    # own `check_antennas` materialises them the same way before measuring.
    if all(net.getWire() is None for net in block.getNets()):
        info("no detailed routing found; building net wires from the route guides")
        checker.makeNetWiresFromGuides(list(block.getNets()))

    candidates = nets_to_check(block, spans)
    info(f"checking {len(candidates)} multi-tile nets against their stitched span")

    level_names = routing_level_names(reader.tech)
    records: list[dict[str, Any]] = []
    for net, span in candidates:
        for violation in checker.getAntennaViolations(net, None, margin_for_span(span)):
            level = violation.routing_level
            records.append(
                {
                    "net": net.getName(),
                    "span": span,
                    "layer": level_names.get(level, f"routing level {level}"),
                    # At this margin the excess over the scaled limit is exactly
                    # the ratio the net reaches once the fabric is stitched,
                    # expressed as a multiple of the PDK limit.
                    "predicted_headroom": violation.excess_ratio,
                    "targets": gate_pins(net),
                }
            )

    records.sort(key=lambda record: -record["predicted_headroom"])
    return records


@click.option(
    "--spans",
    required=True,
    type=click.Path(exists=True, dir_okay=False),
    help="JSON object mapping each declared wire name to its span in tiles.",
)
@click.option(
    "--summary",
    required=True,
    type=click.Path(dir_okay=False),
    help="Where to write the predicted violations as JSON.",
)
@click.command()
@click_odb
def antenna_precheck(reader: Any, spans: str, summary: str) -> None:  # noqa: ANN401
    """Predict which of this tile's wires will violate once the fabric is built."""
    span_map = json.loads(Path(spans).read_text())
    records = predict(reader, span_map)

    for record in records:
        info(
            f"{record['net']} on {record['layer']} reaches "
            f"{record['predicted_headroom']:.2f}x its limit at span "
            f"{record['span']}"
        )
    if not records:
        info("no wire is predicted to violate its antenna ratio once stitched")
    else:
        warn(
            f"{len(records)} wires are predicted to violate their antenna ratio "
            "once the fabric is stitched"
        )

    Path(summary).write_text(json.dumps(records, indent=2))


if __name__ == "__main__":
    antenna_precheck()
