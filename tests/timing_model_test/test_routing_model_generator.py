"""Tests for the folded RoutingModelGenerator.

Covers the no-timing path (placeholder delays, folding the old gen_npnr_model) and
the per-fabric pip-delay caching (folding the old FABulousTimingModelInterface).
"""

from pathlib import Path

import pytest
import pytest_mock

from fabulous.fabric_definition.cell_spec import CellSpec, StdCellLibrary
from fabulous.fabulous_cli.fabulous_cli import FABulous_CLI
from fabulous.routing_model.generator import (
    PLACEHOLDER_PIP_DELAY,
    RoutingModelGenerator,
)
from fabulous.routing_model.tile_timing_model import TimingModelMode


def _library(liberty: list[Path]) -> StdCellLibrary:
    """Build a standard-cell library with the given liberty files and a buffer."""
    return StdCellLibrary(
        liberty_files=liberty,
        cells={"buffer": [CellSpec(cell="buf", input_ports=["A"], output_ports=["X"])]},
    )


def _pip_data_lines(pips: str) -> list[str]:
    """Return only the pip data lines (skip blank and ``#`` comment lines)."""
    return [
        line
        for line in pips.splitlines()
        if line.strip() and not line.lstrip().startswith("#")
    ]


def test_generate_without_timing_uses_placeholder_delays(cli: FABulous_CLI) -> None:
    """Without a timing config every pip carries the placeholder delay."""
    fabric = cli.fabulousAPI.fabric

    pips, bel, belv2, constraints = RoutingModelGenerator(fabric).generate()

    assert isinstance(pips, str)
    assert isinstance(bel, str)
    assert isinstance(belv2, str)
    assert isinstance(constraints, str)

    data_lines = _pip_data_lines(pips)
    assert data_lines, "expected at least one pip in the demo fabric"

    # Pip line format: srcTile,srcWire,dstTile,dstWire,delay,name
    delays = {line.split(",")[4] for line in data_lines}
    assert delays == {str(PLACEHOLDER_PIP_DELAY)}


def test_pip_delay_with_timing_delegates_and_caches(
    cli: FABulous_CLI, mocker: pytest_mock.MockerFixture
) -> None:
    """With a timing config, pip delays come from per-tile engines and are cached."""
    fabric = cli.fabulousAPI.fabric

    calls: list[tuple[str, str, str]] = []

    class FakeTileTimingModel:
        def __init__(self, *, tile_name: str, **_kwargs: object) -> None:
            self.tile_name = tile_name

        def pip_delay(self, src_pip: str, dst_pip: str) -> float:
            calls.append((self.tile_name, src_pip, dst_pip))
            return 1.5

    mocker.patch(
        "fabulous.routing_model.generator.FABulousTileTimingModel",
        FakeTileTimingModel,
    )
    # Timing is enabled, so the generator checks the PDK and loads the
    # standard-cell library before building the (faked) per-tile models.
    mocker.patch(
        "fabulous.routing_model.generator.get_context",
        return_value=mocker.Mock(
            pdk="sky130A", pdk_root=Path("/pdks"), proj_dir=Path("/proj")
        ),
    )
    mocker.patch(
        "fabulous.routing_model.generator.StdCellLibrary.load",
        return_value=_library([Path("/cells.lib")]),
    )

    gen = RoutingModelGenerator(
        fabric,
        mode=TimingModelMode.PHYSICAL,
        verilog_files=[Path("/does/not/matter/top.v")],
    )
    tile_name = next(iter(fabric.tileDic))

    first = gen._pip_delay(tile_name, "LB_O", "JN2BEG3")  # noqa: SLF001
    second = gen._pip_delay(tile_name, "LB_O", "JN2BEG3")  # noqa: SLF001

    assert first == 1.5
    assert second == 1.5
    # Delegated once; the second identical lookup is served from the cache.
    assert calls == [(tile_name, "LB_O", "JN2BEG3")]


def test_timing_requires_verilog_files(cli: FABulous_CLI) -> None:
    """Enabling timing without Verilog sources is rejected up front."""
    fabric = cli.fabulousAPI.fabric

    with pytest.raises(ValueError, match="verilog_files is required"):
        RoutingModelGenerator(fabric, mode=TimingModelMode.PHYSICAL)


def test_timing_requires_pdk(
    cli: FABulous_CLI, mocker: pytest_mock.MockerFixture
) -> None:
    """Enabling timing with no PDK set is rejected up front."""
    fabric = cli.fabulousAPI.fabric

    mocker.patch(
        "fabulous.routing_model.generator.get_context",
        return_value=mocker.Mock(pdk=None),
    )

    with pytest.raises(ValueError, match="FAB_PDK is not set"):
        RoutingModelGenerator(
            fabric,
            mode=TimingModelMode.PHYSICAL,
            verilog_files=[Path("/does/not/matter/top.v")],
        )


def test_timing_requires_configured_liberty(
    cli: FABulous_CLI, mocker: pytest_mock.MockerFixture
) -> None:
    """Enabling timing with no liberty configured for the PDK is rejected up front."""
    fabric = cli.fabulousAPI.fabric

    mocker.patch(
        "fabulous.routing_model.generator.get_context",
        return_value=mocker.Mock(
            pdk="sky130A", pdk_root=Path("/pdks"), proj_dir=Path("/proj")
        ),
    )
    mocker.patch(
        "fabulous.routing_model.generator.StdCellLibrary.load",
        return_value=_library([]),
    )

    with pytest.raises(ValueError, match="No liberty files configured"):
        RoutingModelGenerator(
            fabric,
            mode=TimingModelMode.PHYSICAL,
            verilog_files=[Path("/does/not/matter/top.v")],
        )
