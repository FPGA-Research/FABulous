"""Tests for the FABulousLoopBreakSDC step."""

from pathlib import Path

import pytest
from librelane.common.types import Path as ViewPath
from librelane.config.config import Config
from librelane.state.design_format import DesignFormat
from librelane.steps.step import StepException
from pytest_mock import MockerFixture

from fabulous.fabric_generator.gds_generator.steps.loop_break_sdc import (
    FABulousLoopBreakSDC,
)

_MODULE = "fabulous.fabric_generator.gds_generator.steps.loop_break_sdc"


def _step(
    mocker: MockerFixture, tmp_path: Path, **config: str | list[str] | None
) -> FABulousLoopBreakSDC:
    step = FABulousLoopBreakSDC()
    step.step_dir = str(tmp_path)
    step.toolbox = mocker.Mock()
    step.config = Config(
        {
            "DESIGN_NAME": "tile",
            "CELL_LIBS": {},
            "SYNTH_CORNER": None,
            "FABULOUS_BEL_MODULES": ["bel"],
            **config,
        }
    )
    return step


@pytest.mark.parametrize(
    ("pnr_sdc", "base"),
    [
        pytest.param("pnr", "pnr", id="pnr-sdc"),
        pytest.param(None, "fallback", id="fallback-sdc"),
    ],
)
def test_run_writes_sdc_view(
    mocker: MockerFixture, tmp_path: Path, pnr_sdc: str | None, base: str
) -> None:
    """The SDC view is a librelane path to the base SDC followed by the cuts."""
    for name in ("pnr", "fallback"):
        (tmp_path / f"{name}.sdc").write_text(f"# {name}")
    mocker.patch(f"{_MODULE}.YosysJson.from_netlist")
    mocker.patch(f"{_MODULE}.loop_break_nets", return_value=["j"])
    step = _step(
        mocker,
        tmp_path,
        PNR_SDC_FILE=pnr_sdc and str(tmp_path / f"{pnr_sdc}.sdc"),
        FALLBACK_SDC=str(tmp_path / "fallback.sdc"),
    )

    views, metrics = step.run({DesignFormat.NETLIST: ViewPath("tile.nl.v")})

    sdc = views[DesignFormat.SDC]
    assert isinstance(sdc, ViewPath)
    text = Path(str(sdc)).read_text()
    assert text.startswith(f"# {base}")
    assert "set_disable_timing [fabulous_loop_break_driver {j}]" in text
    assert metrics == {"timing__loop_break__count": 1}


def test_run_rejects_unset_bel_modules(mocker: MockerFixture, tmp_path: Path) -> None:
    """Without the BEL modules the cuts could land inside a BEL."""
    step = _step(mocker, tmp_path, FABULOUS_BEL_MODULES=None)

    with pytest.raises(StepException, match="FABULOUS_BEL_MODULES"):
        step.run({DesignFormat.NETLIST: ViewPath("tile.nl.v")})
