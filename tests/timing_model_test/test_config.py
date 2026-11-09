"""Tests for resolving the source files of one macro."""

from pathlib import Path

import pytest

from fabulous.fabric_cad.timing_model.config import (
    PhysicalSources,
    StructuralSources,
    TimingModelConfig,
    TimingModelMode,
    TimingModelTileSourceFiles,
    resolve_sources,
)

PROJECT_FILES = (
    "Tile/T/T.v",
    "Tile/T/T_switch_matrix.v",
    "Fabric/models_pack.v",
    "Tile/T/notes.txt",
    "Tile/T/macro/final_views/nl/T.nl.v",
    "Tile/T/macro/final_views/spef/nom/T.nom.spef",
    "Tile/T/macro/final_views/spef/nom/T.alt.spef",
    "user_design/top.v",
    "Test/tb.v",
    "Fabric/yosys/blackbox.v",
    "custom/a.v",
    "custom/sub/b.v",
    "custom/c.vh",
)


@pytest.fixture
def project(tmp_path: Path) -> Path:
    """Create a project holding RTL, GDS flow outputs and excluded files."""
    for name in PROJECT_FILES:
        path = tmp_path / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.touch()
    return tmp_path


def make_config(
    project: Path,
    *,
    mode: TimingModelMode,
    consider_wire_delay: bool = True,
    overrides: dict[str, TimingModelTileSourceFiles] | None = None,
) -> TimingModelConfig:
    """Return the settings of `project`."""
    return TimingModelConfig(
        project_dir=project,
        liberty_files=project / "cells.lib",
        min_buf_cell_and_ports="BUF A Y",
        mode=mode,
        consider_wire_delay=consider_wire_delay,
        custom_per_tile_source_files=overrides,
    )


DEFAULT_RTL = {
    "Tile/T/T.v",
    "Tile/T/T_switch_matrix.v",
    "Fabric/models_pack.v",
    "custom/a.v",
    "custom/sub/b.v",
}


@pytest.mark.parametrize(
    ("tile", "rtl", "expected"),
    [
        pytest.param("T", None, DEFAULT_RTL, id="project-search"),
        pytest.param("T", "custom/a.v", {"custom/a.v"}, id="single-file"),
        pytest.param(
            "T",
            ["custom/a.v", "Tile/T/T.v"],
            {"custom/a.v", "Tile/T/T.v"},
            id="file-list",
        ),
        pytest.param("T", "custom/*.v", {"custom/a.v", "custom/sub/b.v"}, id="glob"),
        pytest.param("U", "custom/a.v", DEFAULT_RTL, id="other-tile-override"),
    ],
)
def test_structural_rtl_files(
    project: Path, tile: str, rtl: list[str] | str | None, expected: set[str]
) -> None:
    """The project search skips excluded directories; an override replaces it."""
    overrides = None
    if rtl is not None:
        files = (
            [project / path for path in rtl] if isinstance(rtl, list) else project / rtl
        )
        overrides = {tile: TimingModelTileSourceFiles(rtl_files=files)}
    config = make_config(project, mode=TimingModelMode.STRUCTURAL, overrides=overrides)

    sources = resolve_sources(config, top="T")

    assert isinstance(sources, StructuralSources)
    assert {path.relative_to(project).as_posix() for path in sources.rtl_files} == (
        expected
    )


NETLIST = "Tile/T/macro/final_views/nl/T.nl.v"
SPEF = "Tile/T/macro/final_views/spef/nom/T.nom.spef"
ALT_SPEF = "Tile/T/macro/final_views/spef/nom/T.alt.spef"


@pytest.mark.parametrize(
    ("consider_wire_delay", "netlist_file", "rc_file", "netlist", "spef"),
    [
        pytest.param(True, None, None, NETLIST, (SPEF,), id="defaults"),
        pytest.param(False, None, None, NETLIST, (), id="no-wire-delay"),
        pytest.param(
            True, "custom/a.v", ALT_SPEF, "custom/a.v", (ALT_SPEF,), id="overrides"
        ),
        pytest.param(
            False, None, ALT_SPEF, NETLIST, (), id="rc-override-without-wire-delay"
        ),
    ],
)
def test_physical_sources(
    project: Path,
    consider_wire_delay: bool,
    netlist_file: str | None,
    rc_file: str | None,
    netlist: str,
    spef: tuple[str, ...],
) -> None:
    """The layout files default to the GDS flow outputs of the macro."""
    overrides = TimingModelTileSourceFiles(
        netlist_file=None if netlist_file is None else project / netlist_file,
        rc_file=None if rc_file is None else project / rc_file,
    )
    config = make_config(
        project,
        mode=TimingModelMode.PHYSICAL,
        consider_wire_delay=consider_wire_delay,
        overrides={"T": overrides},
    )

    sources = resolve_sources(config, top="T")

    assert isinstance(sources, PhysicalSources)
    assert sources.netlist_file == project / netlist
    assert sources.spef_files == tuple(project / path for path in spef)


@pytest.mark.parametrize(
    ("mode", "overrides", "missing"),
    [
        pytest.param(
            TimingModelMode.STRUCTURAL,
            TimingModelTileSourceFiles(rtl_files=Path("absent.v")),
            "absent.v",
            id="rtl",
        ),
        pytest.param(
            TimingModelMode.PHYSICAL,
            TimingModelTileSourceFiles(netlist_file=Path("absent.nl.v")),
            "absent.nl.v",
            id="netlist",
        ),
        pytest.param(
            TimingModelMode.PHYSICAL,
            TimingModelTileSourceFiles(rc_file=Path("absent.spef")),
            "absent.spef",
            id="parasitics",
        ),
    ],
)
def test_missing_source_file_raises(
    project: Path,
    mode: TimingModelMode,
    overrides: TimingModelTileSourceFiles,
    missing: str,
) -> None:
    """Every resolved file must exist before any tool runs."""
    config = make_config(project, mode=mode, overrides={"T": overrides})

    with pytest.raises(FileNotFoundError, match=missing):
        resolve_sources(config, top="T")


def test_physical_default_netlist_must_exist(project: Path) -> None:
    """A macro without a finished GDS flow cannot be timed physically."""
    config = make_config(project, mode=TimingModelMode.PHYSICAL)

    with pytest.raises(FileNotFoundError, match="U.nl.v"):
        resolve_sources(config, top="U")
