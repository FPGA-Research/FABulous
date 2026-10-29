"""Tests for the OpenROAD steps that read the input SDC view."""

import pytest
from librelane.common.types import Path
from librelane.config.config import Config
from librelane.state.design_format import DesignFormat
from librelane.steps import openroad as OpenROAD
from pytest_mock import MockerFixture

from fabulous.fabric_generator.gds_generator.steps import state_sdc as StateSDC


@pytest.mark.parametrize(
    ("step_cls", "librelane_cls"),
    [
        pytest.param(StateSDC.FillInsertion, OpenROAD.FillInsertion, id="fill"),
        pytest.param(StateSDC.RCX, OpenROAD.RCX, id="rcx"),
        pytest.param(StateSDC.IRDropReport, OpenROAD.IRDropReport, id="irdrop"),
    ],
)
def test_run_reads_input_sdc_view(
    mocker: MockerFixture,
    step_cls: type[StateSDC.StateSDCStep],
    librelane_cls: type[OpenROAD.OpenROADStep],
) -> None:
    """The librelane step runs with `PNR_SDC_FILE` set to the input SDC view."""
    seen: list[Path | None] = []
    mocker.patch.object(
        librelane_cls,
        "run",
        lambda self, _state_in: seen.append(self.config["PNR_SDC_FILE"]) or ({}, {}),
    )
    step = step_cls()
    step.config = Config({"PNR_SDC_FILE": None})

    step.run({DesignFormat.SDC: Path("cuts.sdc")})

    assert seen == [Path("cuts.sdc")]
    assert step_cls.id == librelane_cls.id
    assert DesignFormat.SDC in step_cls.inputs
