"""Tests for timing-model command target and output selection."""

from pathlib import Path

import pytest
from pytest_mock import MockerFixture

from fabulous.fabric_cad.timing_model.models import TimingModelTarget
from fabulous.fabulous_repl.fabulous_repl import FABulousREPL


@pytest.mark.parametrize(
    ("target_option", "expected_target"),
    [
        pytest.param("", TimingModelTarget.BOTH, id="default-both"),
        pytest.param("--target pips", TimingModelTarget.PIPS, id="pips"),
        pytest.param("--target bels", TimingModelTarget.BELS, id="bels"),
    ],
)
def test_timing_command_passes_target_and_output_paths_to_api(
    cli: FABulousREPL,
    mocker: MockerFixture,
    tmp_path: Path,
    target_option: str,
    expected_target: TimingModelTarget,
) -> None:
    """CLI target selection reaches the API without changing existing defaults."""
    resolved_config = mocker.Mock()
    resolved_config.model_dump_json.return_value = "{}"
    timing_api = mocker.patch.object(
        cli.fabulousAPI,
        "timing_model_interface",
        return_value=resolved_config,
    )
    pip_path = tmp_path / "custom-pips.txt"
    bel_path = tmp_path / "custom-bel.v3.txt"

    cli.onecmd_plus_hooks(
        f"timing_model --mode structural {target_option} "
        f"--outfile {pip_path} --bel-outfile {bel_path}"
    )

    timing_api.assert_called_once_with(
        mode="structural",
        output_file=pip_path,
        debug=cli.debug,
        manual_config=None,
        target=expected_target,
        bel_output_file=bel_path,
    )


def test_timing_api_passes_target_to_nextpnr_writer(
    cli: FABulousREPL, mocker: MockerFixture, tmp_path: Path
) -> None:
    """The public API keeps its existing call shape and forwards output selection."""
    manual_config = mocker.Mock()
    fabric = mocker.Mock()
    cli.fabulousAPI.fabric = fabric
    timing_interface = mocker.patch(
        "fabulous.fabulous_api.FABulousTimingModelInterface"
    )
    timing_writer = mocker.patch(
        "fabulous.fabulous_api.model_gen_npnr.write_nextpnr_timing_files"
    )
    pip_path = tmp_path / "pips.txt"
    bel_path = tmp_path / "bel.v3.txt"

    result = cli.fabulousAPI.timing_model_interface(
        mode="structural",
        output_file=pip_path,
        debug=False,
        manual_config=manual_config,
        target=TimingModelTarget.BELS,
        bel_output_file=bel_path,
    )

    assert result is manual_config
    timing_interface.assert_called_once_with(config=manual_config, fabric=fabric)
    timing_writer.assert_called_once_with(
        fabric=fabric,
        pip_output_file=pip_path,
        bel_output_file=bel_path,
        delay_model=timing_interface.return_value,
        target=TimingModelTarget.BELS,
    )
