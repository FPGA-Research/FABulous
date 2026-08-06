"""FABulous GDS Generator - fabric antenna pre-check step.

Runs on a routed tile and reports the antenna ratios that tile's wires will reach
once the fabric is stitched. See `antenna_precheck.md` beside this file for why a
tile cannot see this on its own.

The measurement is OpenROAD's, in `script/odb_antenna_precheck.py`. What lives
here is the fabric knowledge either side of it: how far each declared wire
travels, which is the one thing OpenROAD cannot work out for itself, and what to
do with the verdicts that come back.
"""

import json
from dataclasses import dataclass
from decimal import Decimal
from importlib import resources
from pathlib import Path

from librelane.common.types import Path as LibreLanePath
from librelane.config.variable import Variable
from librelane.state.state import State
from librelane.steps.checker import MetricChecker
from librelane.steps.odb import OdbpyStep
from librelane.steps.step import MetricsUpdate, Step, StepException, ViewsUpdate
from loguru import logger

from fabulous.fabric_definition.fabric import Fabric
from fabulous.fabric_definition.port import Port
from fabulous.fabric_definition.supertile import SuperTile
from fabulous.fabric_definition.switch_matrix import SwitchMatrix
from fabulous.fabric_definition.tile import Tile
from fabulous.fabric_generator.parser.parse_csv import parseFabricCSV

VIOLATION_COUNT_METRIC = "fabulous__antenna_predicted_violation__count"
WORST_RATIO_METRIC = "fabulous__antenna_predicted_ratio__max"

SPANS_FILE = "antenna_spans.json"
SUMMARY_FILE = "antenna_precheck.json"

# Ratios are reported to four decimal places, so a rerun that changes nothing
# reports an identical metric rather than drifting in the last digits.
METRIC_PRECISION = Decimal("0.0001")

# Configuration buses are distributed across a whole row or column rather than
# following a port offset, so their span comes from the fabric dimensions.
_ROW_SPANNING_NETS = ("FrameData",)
_COLUMN_SPANNING_NETS = ("FrameStrobe",)


def _offset_span(port: Port) -> int:
    """Return how many tiles a port's wire crosses.

    Parameters
    ----------
    port : Port
        The declared port.

    Returns
    -------
    int
        Tile count, at least 1.
    """
    return max(1, abs(port.xOffset) + abs(port.yOffset))


def wire_spans(
    fabric: Fabric, tile: Tile, span_override: int | None = None
) -> dict[str, int]:
    """Return every wire worth checking, mapped to how far it travels.

    Parameters
    ----------
    fabric : Fabric
        The parent fabric, supplying the configuration bus dimensions.
    tile : Tile
        The tile being hardened.
    span_override : int | None
        Apply this span to every wire instead of reading per-port offsets. Use
        when no fabric model is available; it over-reports for shorter wires.

    Returns
    -------
    dict[str, int]
        Span keyed by declared wire name, widest first. Bus bits are not listed
        individually: the checker matches `FrameData[7]` against `FrameData`.
    """
    spans: dict[str, int] = {}

    for port in tile.portsInfo:
        for name in (port.name, port.sourceName, port.destinationName):
            if not name:
                continue
            span = span_override or _offset_span(port)
            # A port can appear under several names; the widest span wins.
            spans[name] = max(spans.get(name, 0), span)

    for name in _ROW_SPANNING_NETS:
        spans[name] = span_override or fabric.numberOfColumns
    for name in _COLUMN_SPANNING_NETS:
        spans[name] = span_override or fabric.numberOfRows

    return dict(sorted(spans.items(), key=lambda item: (-item[1], item[0])))


@dataclass(frozen=True)
class PredictedViolation:
    """A wire predicted to exceed its antenna ratio once the fabric is stitched.

    Attributes
    ----------
    tile : str
        Tile type the wire was measured in.
    net : str
        Net name, including its bus index.
    layer : str
        Routing layer that exceeds its limit.
    span : int
        Number of tiles the wire runs across.
    headroom : Decimal
        Predicted antenna ratio as a multiple of the PDK limit for that layer.
        Anything above 1 is a violation; 2 is twice the permitted ratio.
    targets : tuple[str, ...]
        The `instance/pin` sinks on this net that a diode would protect.
    """

    tile: str
    net: str
    layer: str
    span: int
    headroom: Decimal
    targets: tuple[str, ...]


def parse_summary(summary: Path, tile_name: str) -> list[PredictedViolation]:
    """Read the checker's JSON and return the violations it predicted.

    Parameters
    ----------
    summary : Path
        The file written by `odb_antenna_precheck.py`.
    tile_name : str
        Tile type the run covered, recorded on each violation.

    Returns
    -------
    list[PredictedViolation]
        All predicted violations, worst headroom first.
    """
    # The ratios are carried as Decimal from the moment they are read, so the
    # metric this step reports is the number the checker wrote, not a binary
    # approximation of it.
    records = json.loads(summary.read_text(), parse_float=Decimal)

    violations = [
        PredictedViolation(
            tile=tile_name,
            net=record["net"],
            layer=record["layer"],
            span=int(record["span"]),
            headroom=Decimal(record["predicted_headroom"]),
            targets=tuple(record["targets"]),
        )
        for record in records
    ]
    violations.sort(key=lambda violation: -violation.headroom)

    logger.info(
        f"predicted {len(violations)} stitched antenna violations in {tile_name}"
    )
    return violations


def diode_targets(violations: list[PredictedViolation]) -> list[dict[str, str]]:
    """Turn predicted violations into a diode list `Odb.InsertECODiodes` accepts.

    This is the payoff of predicting early: instead of `DIODE_ON_PORTS: both`
    paying diode area on every port of every tile, only these sinks need one.

    Parameters
    ----------
    violations : list[PredictedViolation]
        Predicted violations, as returned by `parse_summary`.

    Returns
    -------
    list[dict[str, str]]
        One `{"target": "instance/pin"}` entry per sink, worst wire first and
        de-duplicated: a net violating on two layers still needs one diode.
    """
    targets: list[dict[str, str]] = []
    seen: set[str] = set()
    for violation in violations:
        for target in violation.targets:
            if target in seen:
                continue
            seen.add(target)
            targets.append({"target": target})
    return targets


def _placeholder_tile(name: str) -> Tile:
    """Build a portless tile, for when only a uniform span is in force."""
    return Tile(
        name=name,
        ports=[],
        bels=[],
        tileDir=Path(),
        switch_matrix=SwitchMatrix(matrix_file=Path(), connections={}),
        gen_ios=[],
        userCLK=False,
        pinOrderConfig={},
    )


def _as_tile(value: object, name: str) -> Tile | None:
    """Normalise a configured tile object into something carrying `portsInfo`.

    Parameters
    ----------
    value : object
        The `FABULOUS_TILE` value: a `Tile`, a `SuperTile`, or None.
    name : str
        Design name, used when flattening a super tile.

    Returns
    -------
    Tile | None
        The tile, a stand-in carrying every sub-tile's ports for a super tile,
        or None when nothing usable was configured.
    """
    if isinstance(value, Tile):
        return value
    if isinstance(value, SuperTile):
        # A super tile's wires are declared on its sub-tiles; the boundary nets
        # of the hardened macro can come from any of them.
        flattened = _placeholder_tile(name)
        for sub_tile in value.tiles:
            flattened.portsInfo.extend(sub_tile.portsInfo)
        return flattened
    return None


@Step.factory.register()
class FABulousAntennaPrecheck(OdbpyStep):
    """Predict stitched antenna ratios from a single routed tile.

    Holds every multi-tile wire to its antenna limit divided by the span its port
    declares, which is arithmetically the same as giving it the metal it will
    carry once abutted, and reports the wires that fail. The sinks at risk are
    written to `diode_targets.json` in the form `Odb.InsertECODiodes` accepts, so
    diodes can be placed only where they are needed instead of on every port.

    Notes
    -----
    Metrics:
        fabulous__antenna_predicted_violation__count : int
            Number of (net, layer) pairs predicted to violate once stitched.
        fabulous__antenna_predicted_ratio__max : Decimal
            Worst predicted antenna ratio, as a multiple of its layer's limit.
    """

    id = "FABulous.AntennaPrecheck"
    name = "FABulous Antenna Pre-check"
    long_name = "FABulous Fabric-Level Antenna Pre-check"

    # Reads the routed database and reports on it; it alters nothing.
    outputs = []

    config_vars = [
        Variable(
            "RUN_FABULOUS_ANTENNA_PRECHECK",
            bool,
            "Predict fabric-level antenna ratios while hardening each tile.",
            default=True,
        ),
        # Reuses the names the fabric-side flows already use. Declared optional
        # here because the tile flow can run without a parent fabric; the fabric
        # flows keep their own required declarations, and no flow holds both a
        # fabric step and this tile-only one.
        Variable(
            "FABULOUS_TILE",
            Tile | SuperTile | None,
            "The tile being hardened. The tile flows are handed this object "
            "already, so passing it on avoids re-parsing any CSV.",
            default=None,
        ),
        Variable(
            "FABULOUS_FABRIC",
            Fabric | None,
            "The parent fabric. Supplies the tile's declared port offsets plus "
            "the row and column counts that `FrameStrobe` and `FrameData` span.",
            default=None,
        ),
        Variable(
            "FABULOUS_FABRIC_CONFIG",
            list[LibreLanePath] | None,
            "Path to the parent fabric CSV, parsed when 'FABULOUS_FABRIC' is not "
            "already an object. Only the first entry is used.",
            default=None,
        ),
        Variable(
            "FABULOUS_ANTENNA_MAX_SPAN",
            int | None,
            "Apply this span to every wire instead of reading per-port offsets. "
            "A blunt, conservative gate for when the parent fabric is not "
            "available; it over-reports for wires shorter than this.",
            default=None,
        ),
    ]

    def get_script_path(self) -> str:
        """Return the path to the ODB antenna prediction script."""
        return str(
            resources.files("fabulous.fabric_generator.gds_generator.script")
            / "odb_antenna_precheck.py"
        )

    def get_command(self) -> list[str]:
        """Return the command, pointing the script at the span map it needs."""
        step_dir = Path(self.step_dir)
        return super().get_command() + [
            "--spans",
            str(step_dir / SPANS_FILE),
            "--summary",
            str(step_dir / SUMMARY_FILE),
        ]

    def span_context(self) -> tuple[Tile, Fabric]:
        """Return the tile and fabric that say how far each wire travels.

        Both come from objects the flow already built: the tile flow is handed a
        `Tile` and passes it on as `FABULOUS_TILE`, and the fabric flows carry a
        `Fabric` as `FABULOUS_FABRIC`. Parsing the fabric CSV is a last resort
        for a tile hardened outside a flow that has either.

        Returns
        -------
        tuple[Tile, Fabric]
            The tile whose ports carry the offsets, and the fabric whose
            dimensions the configuration buses span.

        Raises
        ------
        StepException
            If nothing at all says how far wires travel, or the fabric CSV is
            given but cannot be parsed.
        """
        design_name = str(self.config["DESIGN_NAME"])
        max_span = self.config.get("FABULOUS_ANTENNA_MAX_SPAN")

        fabric = self.config.get("FABULOUS_FABRIC")
        fabric = fabric if isinstance(fabric, Fabric) else None
        tile = _as_tile(self.config.get("FABULOUS_TILE"), design_name)

        # Only parse if the objects did not already answer the question.
        if (tile is None or fabric is None) and (
            entries := self.config.get("FABULOUS_FABRIC_CONFIG")
        ):
            fabric_csv = Path(str(entries[0]))
            try:
                parsed = parseFabricCSV(str(fabric_csv))
            except Exception as exc:
                raise StepException(
                    f"could not parse fabric CSV {fabric_csv}: {exc}"
                ) from exc
            fabric = fabric or parsed
            tile = tile or parsed.tileDic.get(design_name)

        if tile is None and fabric is not None:
            tile = fabric.tileDic.get(design_name)

        if tile is None and max_span is None:
            raise StepException(
                f"'{self.id}' needs to know how far wires travel, and nothing "
                f"declares the ports of tile {design_name!r}. Set "
                "'FABULOUS_TILE', 'FABULOUS_FABRIC' or 'FABULOUS_FABRIC_CONFIG', "
                "or 'FABULOUS_ANTENNA_MAX_SPAN' for a uniform conservative span."
            )

        if fabric is None:
            # Routing wires still get their real spans from the tile's ports;
            # only the configuration buses need fabric dimensions.
            self.warn(
                "no parent fabric available, so the FrameData and FrameStrobe "
                "spans are unknown and those nets are checked as if they stayed "
                "within one tile. Set 'FABULOUS_FABRIC' or "
                "'FABULOUS_FABRIC_CONFIG' to cover them."
            )
            fabric = Fabric(
                fabric_dir=Path(), tile=[], numberOfRows=1, numberOfColumns=1
            )

        return tile or _placeholder_tile(design_name), fabric

    def _write_reports(self, violations: list[PredictedViolation]) -> None:
        """Write the human-readable report and the diode target list."""
        report = Path(self.step_dir) / "antenna_precheck.rpt"
        lines = [
            f"{'tile':<16} {'net':<28} {'layer':<8} {'span':>5} "
            f"{'x over limit':>13}  sinks",
        ]
        lines.extend(
            f"{v.tile:<16} {v.net:<28} {v.layer:<8} {v.span:>5} "
            f"{v.headroom:>13.2f}  {', '.join(v.targets)}"
            for v in violations
        )
        report.write_text("\n".join(lines) + "\n")

        targets = Path(self.step_dir) / "diode_targets.json"
        targets.write_text(json.dumps(diode_targets(violations), indent=2))

    def run(
        self,
        state_in: State,
        **kwargs: str,
    ) -> tuple[ViewsUpdate, MetricsUpdate]:
        """Predict this tile's stitched antenna ratios and report them.

        Parameters
        ----------
        state_in : State
            Incoming state; supplies the routed ODB.
        **kwargs : str
            Forwarded to the underlying ODB step.

        Returns
        -------
        tuple[ViewsUpdate, MetricsUpdate]
            No view updates, plus the predicted violation count and worst ratio.
        """
        tile, fabric = self.span_context()
        design_name = str(self.config["DESIGN_NAME"])

        max_span = self.config.get("FABULOUS_ANTENNA_MAX_SPAN")
        spans = wire_spans(
            fabric, tile, span_override=int(max_span) if max_span else None
        )
        multi_tile = {name: span for name, span in spans.items() if span > 1}
        if not multi_tile:
            self.warn(
                f"tile {design_name!r} declares no wire that leaves it, so there "
                "is nothing to pre-check."
            )
            return {}, {VIOLATION_COUNT_METRIC: 0, WORST_RATIO_METRIC: Decimal(0)}

        step_dir = Path(self.step_dir)
        step_dir.mkdir(parents=True, exist_ok=True)
        (step_dir / SPANS_FILE).write_text(json.dumps(multi_tile, indent=2))

        views_updates, metrics_updates = super().run(state_in, **kwargs)

        violations = parse_summary(step_dir / SUMMARY_FILE, tile.name)
        self._write_reports(violations)

        worst = max((v.headroom for v in violations), default=Decimal(0))
        if violations:
            self.warn(
                f"{len(violations)} wires are predicted to violate their antenna "
                f"ratio once the fabric is stitched; worst is {worst:.1f}x its "
                "limit. See antenna_precheck.rpt."
            )
        metrics_updates[VIOLATION_COUNT_METRIC] = len(violations)
        metrics_updates[WORST_RATIO_METRIC] = worst.quantize(METRIC_PRECISION)
        return views_updates, metrics_updates


@Step.factory.register()
class FABulousAntennaPrecheckChecker(MetricChecker):
    """Raise if any wire is predicted to violate once the fabric is stitched."""

    id = "Checker.FABulousAntennaPrecheck"
    name = "FABulous Antenna Pre-check Checker"
    long_name = "FABulous Fabric-Level Antenna Pre-check Checker"

    metric_name = VIOLATION_COUNT_METRIC
    metric_description = "Predicted fabric-level antenna violations"
    deferred = True

    error_on_var = Variable(
        "ERROR_ON_PREDICTED_ANTENNA",
        bool,
        "Fail the flow when a tile is predicted to violate its antenna ratio "
        "once the fabric is stitched. Off by default: the prediction is a guide "
        "for where to place diodes, not sign-off.",
        default=False,
    )
    # A checker's `error_on_var` is only ever read back out of the config, so it
    # has to be declared as a variable too or setting it is rejected as unknown.
    config_vars = [error_on_var]
