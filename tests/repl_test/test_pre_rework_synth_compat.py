"""Tests for the temporary Yosys `synth_fabulous` rework compatibility layer.

TODO(3.0): remove together with `pre_rework_synth_compat_args`.
"""

import re
import subprocess
from pathlib import Path

import pytest
from _pytest.logging import LogCaptureFixture
from pytest_mock import MockerFixture, MockType

from fabulous.fabulous_repl.cmd_user_design import pre_rework_synth_compat_args

PRE_REWORK_HELP = "    -plib <primitive_library.v>\n    -iopad\n"
REWORKED_HELP = "    -cells-map <cells_map>\n    -noiopad\n"


def _mock_synth_help(mocker: MockerFixture, synth_help: str) -> MockType:
    return mocker.patch(
        "fabulous.fabulous_repl.cmd_user_design.sp.run",
        return_value=subprocess.CompletedProcess(
            args=[], returncode=0, stdout=synth_help
        ),
    )


@pytest.mark.parametrize(
    ("project_lib", "synth_help", "args", "expected", "warns"),
    [
        pytest.param(True, None, "-nofsm", "-nofsm", False, id="current-no-probe"),
        pytest.param(
            True,
            PRE_REWORK_HELP,
            "-iopad -nofsm",
            "-iopad -nofsm",
            False,
            id="current-pre_rework_yosys-keeps-iopad",
        ),
        pytest.param(
            True,
            REWORKED_HELP,
            "-iopad -nofsm",
            "-nofsm",
            True,
            id="current-reworked_yosys-drops-iopad",
        ),
        pytest.param(
            False,
            PRE_REWORK_HELP,
            "-iopad -nofsm",
            "-iopad -nofsm",
            False,
            id="pre_rework-pre_rework_yosys-unchanged",
        ),
    ],
)
def test_args_without_injection(
    tmp_path: Path,
    mocker: MockerFixture,
    caplog: LogCaptureFixture,
    *,
    project_lib: bool,
    synth_help: str | None,
    args: str,
    expected: str,
    warns: bool,
) -> None:
    """Only a pre-rework project on a reworked Yosys gets the library injected."""
    if project_lib:
        (tmp_path / "yosys").mkdir()
    probe = _mock_synth_help(mocker, synth_help or "")

    assert pre_rework_synth_compat_args(tmp_path, "yosys", args) == expected
    assert probe.called is (synth_help is not None)
    assert ("deprecated" in caplog.text) is warns


@pytest.mark.parametrize("custom_prims", [False, True])
def test_pre_rework_project_on_reworked_yosys(
    tmp_path: Path,
    mocker: MockerFixture,
    caplog: LogCaptureFixture,
    *,
    custom_prims: bool,
) -> None:
    """The packaged library is injected ahead of the user arguments."""
    prims = tmp_path / "user_design" / "custom_prims.v"
    if custom_prims:
        prims.parent.mkdir()
        prims.touch()
    _mock_synth_help(mocker, REWORKED_HELP)

    result = pre_rework_synth_compat_args(tmp_path, "yosys", "-iopad -nofsm")

    assert "predates the Yosys synth_fabulous rework" in caplog.text
    assert result.endswith(r"-ff \$_DFF_P_ 0 -ff \$_DLATCH_?_ x -nofsm")
    libs = re.findall(
        r"-(?:extra-plib|extra-map|cells-map|arith-map|extra-mlibmap) (\S+)", result
    )
    assert all(Path(lib).is_file() for lib in libs)
    plibs = [Path(lib).name for lib in re.findall(r"-extra-plib (\S+)", result)]
    assert plibs == (["prims.v", "custom_prims.v"] if custom_prims else ["prims.v"])
