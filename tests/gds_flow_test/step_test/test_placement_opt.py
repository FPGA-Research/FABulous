"""Tests for what `PlacementDrivenTileOptimisation` adds to the area optimisation.

The loop body never runs here. What is tested is the bookkeeping around it: the
body it assembles, the die search it refuses, the routing it skips, how it
scores an iteration and the views it exports.
"""

# ruff: noqa: SLF001

from collections.abc import Callable
from decimal import Decimal
from pathlib import Path

import pytest
from librelane.config.config import Config
from librelane.state.state import State
from librelane.steps import openroad as OpenROAD
from pytest_mock import MockerFixture

from fabulous.custom_exception import GDSFlowError
from fabulous.fabric_definition.define import Side
from fabulous.fabric_generator.gds_generator.formats import (
    CONFIG_MEM_FORMAT,
    RECONNECT_FORMAT,
)
from fabulous.fabric_generator.gds_generator.opt.placement_opt import (
    IterationInputs,
    PlacementDrivenTileOptimisation,
)
from fabulous.fabric_generator.gds_generator.steps.apply_config_mapping import (
    ApplyConfigMapping,
)
from fabulous.fabric_generator.gds_generator.steps.dump_placement import DumpPlacement
from fabulous.fabric_generator.gds_generator.steps.propose_config_mapping import (
    ProposeConfigMapping,
)
from fabulous.fabric_generator.gds_generator.steps.tile_area_opt import OptMode
from fabulous.fabric_generator.gds_generator.variables import (
    CONFIG_MAPPING_VARIABLE,
    CONFIG_MEM_CSV_VARIABLE,
    PLACEMENT_ITERATIONS_VARIABLE,
    ROUTE_EVERY_ITERATION_VARIABLE,
)

HEADER = "frame_name,frame_index,bits_used_in_frame,used_bits_mask,ConfigBits_ranges\n"
CSV_A = HEADER + "frame0,0,2,11,1;0\nframe1,1,0,00,# NULL\n"
CSV_B = HEADER + "frame0,0,1,10,1\nframe1,1,1,01,0\n"

ORDER = {
    Side.NORTH: ["N1BEG[1]", "N1BEG[0]"],
    Side.SOUTH: ["N1END[1]", "N1END[0]"],
}

BUDGET = 3


@pytest.fixture
def files(tmp_path: Path) -> dict[str, Path]:
    paths = {
        "csv_a": tmp_path / "T_ConfigMem.csv",
        "csv_b": tmp_path / "proposal.ConfigMem.csv",
        "reconnect": tmp_path / "proposal.reconnect.json",
    }
    paths["csv_a"].write_text(CSV_A)
    paths["csv_b"].write_text(CSV_B)
    paths["reconnect"].write_text("{}")
    return paths


@pytest.fixture
def scored_state(mocker: MockerFixture) -> Callable[[float], State]:
    """Return a state reporting the cost the optimisation still carries."""

    def make(score: float) -> State:
        state = mocker.MagicMock()
        state.metrics = {"fabulous__config_mapping__stub_before": score}
        return state

    return make


@pytest.fixture
def opt_step(
    mock_config: Config, files: dict[str, Path], tmp_path: Path, mocker: MockerFixture
) -> PlacementDrivenTileOptimisation:
    mocker.patch(
        "fabulous.fabric_generator.gds_generator.steps.tile_area_opt.get_pitch",
        return_value=(Decimal("0.46"), Decimal("2.72")),
    )
    mocker.patch(
        "fabulous.fabric_generator.gds_generator.steps.tile_area_opt.get_routing_obstructions",
        return_value=[],
    )
    config = mock_config.copy(
        **{
            CONFIG_MAPPING_VARIABLE.name: True,
            PLACEMENT_ITERATIONS_VARIABLE.name: BUDGET,
            ROUTE_EVERY_ITERATION_VARIABLE.name: False,
            CONFIG_MEM_CSV_VARIABLE.name: str(files["csv_a"]),
            "FABULOUS_OPT_MODE": OptMode.NO_OPT,
            # 218 x-pitches by 24 y-pitches, so rounding leaves the die alone.
            "DIE_AREA": (Decimal(0), Decimal(0), Decimal("100.28"), Decimal("65.28")),
            "FABULOUS_PIN_MIN_WIDTH": Decimal(0),
            "FABULOUS_PIN_MIN_HEIGHT": Decimal(0),
            "FABULOUS_TILE_LOGICAL_WIDTH": 1,
            "FABULOUS_TILE_LOGICAL_HEIGHT": 1,
        }
    )
    step = PlacementDrivenTileOptimisation(config)
    step.config = config
    step.step_dir = str(tmp_path / "step")
    Path(step.step_dir).mkdir()
    step.clean_probes = []
    step._start_run()
    return step


def test_the_optimisation_steps_sit_around_the_loop_body() -> None:
    steps = PlacementDrivenTileOptimisation.Steps
    assert steps[steps.index(OpenROAD.Floorplan) + 1] is ApplyConfigMapping
    cts = steps.index(OpenROAD.CTS)
    assert steps[cts + 1 : cts + 3] == [DumpPlacement, ProposeConfigMapping]
    assert steps[cts + 3] is OpenROAD.GlobalRouting
    assert CONFIG_MEM_FORMAT in PlacementDrivenTileOptimisation.outputs
    assert PlacementDrivenTileOptimisation.propagate_exceptions == (GDSFlowError,)


def test_run_sizes_the_body_by_the_budget(
    opt_step: PlacementDrivenTileOptimisation, mock_state: State, mocker: MockerFixture
) -> None:
    run = mocker.patch(
        "fabulous.fabric_generator.gds_generator.steps.tile_area_opt.WhileStep.run",
        return_value=({}, {}),
    )

    opt_step.run(mock_state)

    assert opt_step.max_iterations == BUDGET
    run.assert_called_once()


@pytest.mark.parametrize(
    ("route_every", "breaks"),
    [(False, True), (True, False)],
    ids=["placement only", "routed"],
)
def test_the_body_stops_after_the_proposals_unless_the_run_routes(
    opt_step: PlacementDrivenTileOptimisation,
    mock_state: State,
    route_every: bool,
    breaks: bool,
) -> None:
    opt_step.config = opt_step.config.copy(
        **{ROUTE_EVERY_ITERATION_VARIABLE.name: route_every}
    )
    propose = ProposeConfigMapping(opt_step.config)

    assert opt_step.mid_iteration_break(mock_state, propose) is breaks


def test_an_iteration_that_never_proposed_is_refused(
    opt_step: PlacementDrivenTileOptimisation, mock_state: State
) -> None:
    """Nothing to export means no iteration reached its proposals."""
    opt_step.last_working_state = None

    with pytest.raises(GDSFlowError, match="nothing to export"):
        opt_step.post_loop_callback(mock_state)


@pytest.mark.parametrize(
    ("scores", "winning_iteration"),
    [((4.0, 9.0), 0), ((9.0, 4.0), 1), ((4.0, 4.0), 0)],
    ids=["first is best", "second is best", "a tie keeps the earlier"],
)
def test_the_iteration_whose_inputs_cost_least_wins(
    opt_step: PlacementDrivenTileOptimisation,
    files: dict[str, Path],
    scored_state: Callable[[float], State],
    scores: tuple[float, ...],
    winning_iteration: int,
) -> None:
    applied = [
        IterationInputs(files["csv_a"], None),
        IterationInputs(files["csv_b"], files["reconnect"]),
    ]

    for inputs, score in zip(applied, scores, strict=True):
        opt_step.applied = inputs
        opt_step._keep_working_state(scored_state(score))

    assert opt_step.winner == applied[winning_iteration]
    assert opt_step.best_score == min(scores)


@pytest.mark.parametrize(
    "full_iter_completed", [False, True], ids=["stopped at its proposals", "routed"]
)
def test_an_iteration_is_kept_and_carried_whether_or_not_it_routed(
    opt_step: PlacementDrivenTileOptimisation,
    files: dict[str, Path],
    scored_state: Callable[[float], State],
    full_iter_completed: bool,
) -> None:
    applied = IterationInputs(files["csv_a"], None)
    opt_step.applied = applied
    state = scored_state(4.0)
    state.metrics |= {"fabulous__config_mapping__unchanged": 0}
    views = {
        CONFIG_MEM_FORMAT.id: str(files["csv_b"]),
        RECONNECT_FORMAT.id: str(files["reconnect"]),
    }
    state.get.side_effect = views.get

    opt_step.post_iteration_callback(state, full_iter_completed)

    assert opt_step.winner == applied
    assert opt_step.last_working_state is not None
    assert opt_step.next_inputs.config_mem_csv == files["csv_b"]
    assert opt_step.converged is False


def test_an_iteration_that_never_proposed_stops_the_search(
    opt_step: PlacementDrivenTileOptimisation, mock_state: State
) -> None:
    with pytest.raises(GDSFlowError, match="never reached its proposals"):
        opt_step._score(mock_state)


@pytest.mark.parametrize(
    ("converged", "iteration", "runs"),
    [(False, 0, True), (False, BUDGET, False), (True, 0, False)],
    ids=["more to do", "budget spent", "converged"],
)
def test_the_loop_runs_until_it_converges_or_spends_its_budget(
    opt_step: PlacementDrivenTileOptimisation,
    mock_state: State,
    converged: bool,
    iteration: int,
    runs: bool,
) -> None:
    opt_step.converged = converged
    opt_step.iteration = iteration

    assert opt_step.condition(mock_state) is runs


def test_post_loop_exports_the_winners_inputs_as_views(
    opt_step: PlacementDrivenTileOptimisation, files: dict[str, Path], mock_state: State
) -> None:
    opt_step.last_working_state = State(
        metrics={**mock_state.metrics, "design__die__bbox": "0 0 10 10"}
    )
    opt_step.winner = IterationInputs(files["csv_b"], files["reconnect"])

    result = opt_step.post_loop_callback(mock_state)

    csv_out = Path(opt_step.step_dir) / "test_design.ConfigMem.csv"
    assert str(result[CONFIG_MEM_FORMAT]) == str(csv_out)
    assert csv_out.read_text() == CSV_B
