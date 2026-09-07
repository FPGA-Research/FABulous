"""Tests for the iteration bookkeeping of `PlacementOptLoop`.

No iteration ever runs here. The tests drive the loop with fake states that
carry the metrics and views a real iteration would leave, so they check what
each iteration implements, which iteration wins, when routing is skipped, how
long the loop runs and what it exports.
"""

from pathlib import Path

import pytest
from librelane.config.config import Config
from pytest_mock import MockerFixture, MockType

from fabulous.custom_exception import GDSFlowError
from fabulous.fabric_definition.define import ConfigBitMode, Side
from fabulous.fabric_generator.gds_generator.formats import (
    CONFIG_MEM_FORMAT,
    RECONNECT_FORMAT,
    TILE_INTERFACE_ORDER_FORMAT,
)
from fabulous.fabric_generator.gds_generator.opt.loop import (
    IterationInputs,
    PlacementOptLoop,
)
from fabulous.fabric_generator.gds_generator.opt.tile_interface import (
    write_interface_order,
)
from fabulous.fabric_generator.gds_generator.opt.variables import (
    CONFIG_BIT_MODE_VARIABLE,
    CONFIG_MAPPING_RECONNECT_VARIABLE,
    CONFIG_MAPPING_TARGET_VARIABLE,
    CONFIG_MAPPING_VARIABLE,
    CONFIG_MEM_CSV_VARIABLE,
    PLACEMENT_ITERATIONS_VARIABLE,
    ROUTE_EVERY_ITERATION_VARIABLE,
    TILE_INTERFACE_FIXED_ORDER_VARIABLE,
    TILE_INTERFACE_ORDER_VARIABLE,
    TILE_INTERFACE_PAIRS_VARIABLE,
    TILE_INTERFACE_VARIABLE,
)

HEADER = "frame_name,frame_index,bits_used_in_frame,used_bits_mask,ConfigBits_ranges\n"
CSV_A = HEADER + "frame0,0,2,11,1;0\nframe1,1,0,00,# NULL\n"
CSV_B = HEADER + "frame0,0,1,10,1\nframe1,1,1,01,0\n"

ORDER = {
    Side.NORTH: ["N1BEG[1]", "N1BEG[0]"],
    Side.SOUTH: ["N1END[1]", "N1END[0]"],
}

GROWTH_CAP = 20
BUDGET = 3


@pytest.fixture
def files(tmp_path: Path) -> dict[str, Path]:
    """The inputs and proposals of an iteration, proposals also as a second copy.

    A proposal always lands in a fresh step directory, so a converged iteration
    is one whose proposal repeats its inputs at a different path.
    """
    paths = {
        "csv_a": tmp_path / "T_ConfigMem.csv",
        "csv_b": tmp_path / "proposal.ConfigMem.csv",
        "csv_b_again": tmp_path / "next_proposal.ConfigMem.csv",
        "reconnect": tmp_path / "proposal.reconnect.json",
        "pairs": tmp_path / "T_pin_pairs.yaml",
    }
    paths["csv_a"].write_text(CSV_A)
    paths["csv_b"].write_text(CSV_B)
    paths["csv_b_again"].write_text(CSV_B)
    paths["reconnect"].write_text("{}")
    paths["pairs"].write_text("- {axis: vertical, first: N1BEG, second: N1END}\n")
    for key in ("order", "order_again", "project_order"):
        paths[key] = tmp_path / f"{key}.interface_order.yaml"
        write_interface_order(ORDER, paths[key])
    return paths


def _config(files: dict[str, Path], **overrides: object) -> Config:
    return Config(
        {
            "DESIGN_NAME": "test_design",
            CONFIG_BIT_MODE_VARIABLE.name: ConfigBitMode.FRAME_BASED,
            CONFIG_MAPPING_VARIABLE.name: True,
            TILE_INTERFACE_VARIABLE.name: True,
            CONFIG_MEM_CSV_VARIABLE.name: str(files["csv_a"]),
            CONFIG_MAPPING_TARGET_VARIABLE.name: None,
            CONFIG_MAPPING_RECONNECT_VARIABLE.name: None,
            TILE_INTERFACE_PAIRS_VARIABLE.name: str(files["pairs"]),
            TILE_INTERFACE_ORDER_VARIABLE.name: None,
            TILE_INTERFACE_FIXED_ORDER_VARIABLE.name: None,
            PLACEMENT_ITERATIONS_VARIABLE.name: BUDGET,
            ROUTE_EVERY_ITERATION_VARIABLE.name: False,
            **overrides,
        }
    )


@pytest.fixture
def config(files: dict[str, Path]) -> Config:
    return _config(files)


@pytest.fixture
def loop(config: Config) -> PlacementOptLoop:
    return PlacementOptLoop(config, growth_cap=GROWTH_CAP, no_opt=True)


def _fake_state(
    mocker: MockerFixture, metrics: dict, views: dict[str, Path] | None = None
) -> MockType:
    """A state stub answering `.metrics` and `.get(id)`."""
    views = views or {}
    state = mocker.MagicMock()
    state.metrics = metrics
    state.get.side_effect = lambda key, default=None: views.get(key, default)
    return state


def _proposal_views(files: dict[str, Path]) -> dict[str, Path]:
    return {
        CONFIG_MEM_FORMAT.id: files["csv_b"],
        RECONNECT_FORMAT.id: files["reconnect"],
        TILE_INTERFACE_ORDER_FORMAT.id: files["order"],
    }


@pytest.mark.parametrize(
    ("override", "message"),
    [
        ({CONFIG_MEM_CSV_VARIABLE.name: None}, CONFIG_MEM_CSV_VARIABLE.name),
        (
            {TILE_INTERFACE_PAIRS_VARIABLE.name: None},
            TILE_INTERFACE_PAIRS_VARIABLE.name,
        ),
        (
            {CONFIG_BIT_MODE_VARIABLE.name: ConfigBitMode.FLIPFLOP_CHAIN},
            "FRAME_BASED, not FLIPFLOP_CHAIN",
        ),
    ],
    ids=["no configuration memory", "no bus pairs", "flip-flop chain"],
)
def test_an_optimisation_without_its_inputs_is_a_fault(
    files: dict[str, Path], override: dict[str, object], message: str
) -> None:
    config = _config(files, **override)
    with pytest.raises(GDSFlowError, match=message):
        PlacementOptLoop(config, growth_cap=GROWTH_CAP, no_opt=True)


def test_both_switches_off_leaves_the_loop_inactive(files: dict[str, Path]) -> None:
    config = _config(
        files,
        **{
            CONFIG_MAPPING_VARIABLE.name: False,
            TILE_INTERFACE_VARIABLE.name: False,
            CONFIG_MEM_CSV_VARIABLE.name: None,
        },
    )

    loop = PlacementOptLoop(config, growth_cap=GROWTH_CAP, no_opt=True)

    assert loop.active is False
    assert loop.next_inputs == IterationInputs(None, None, None)


def test_the_first_iteration_implements_the_tile_mapping_as_written(
    loop: PlacementOptLoop, config: Config, files: dict[str, Path]
) -> None:
    applied = loop.begin_iteration(config)

    assert applied[CONFIG_MAPPING_TARGET_VARIABLE.name] == str(files["csv_a"])
    assert applied[CONFIG_MAPPING_RECONNECT_VARIABLE.name] is None
    assert applied[TILE_INTERFACE_ORDER_VARIABLE.name] is None
    assert loop.iteration == 1


def test_an_iteration_implements_the_previous_proposals(
    loop: PlacementOptLoop, config: Config, files: dict[str, Path]
) -> None:
    loop.next_inputs = IterationInputs(
        files["csv_b"], files["reconnect"], files["order"]
    )

    applied = loop.begin_iteration(config)

    assert applied[CONFIG_MAPPING_TARGET_VARIABLE.name] == str(files["csv_b"])
    assert applied[CONFIG_MAPPING_RECONNECT_VARIABLE.name] == str(files["reconnect"])
    assert applied[TILE_INTERFACE_ORDER_VARIABLE.name] == str(files["order"])
    assert loop.applied == loop.next_inputs


def test_a_project_order_is_the_fixed_order_of_every_iteration(
    files: dict[str, Path],
) -> None:
    config = _config(
        files, **{TILE_INTERFACE_ORDER_VARIABLE.name: str(files["project_order"])}
    )
    loop = PlacementOptLoop(config, growth_cap=GROWTH_CAP, no_opt=True)

    assert loop.fixed_order == files["project_order"]
    assert loop.next_inputs.interface_order == files["project_order"]

    applied = loop.begin_iteration(config)

    assert applied[TILE_INTERFACE_ORDER_VARIABLE.name] == str(files["project_order"])
    assert applied[TILE_INTERFACE_FIXED_ORDER_VARIABLE.name] == str(
        files["project_order"]
    )


def test_a_finished_iteration_hands_its_proposals_to_the_next(
    loop: PlacementOptLoop,
    config: Config,
    files: dict[str, Path],
    mocker: MockerFixture,
) -> None:
    loop.begin_iteration(config)
    state = _fake_state(
        mocker,
        {"design__die__bbox": "0 0 10 10", "route__wirelength": 200},
        _proposal_views(files),
    )

    loop.end_iteration(state, True)

    assert loop.next_inputs == IterationInputs(
        files["csv_b"], files["reconnect"], files["order"]
    )
    assert loop.converged is False
    assert (loop.last_clean, loop.clean_seen) == (True, True)


def test_a_failed_iteration_still_hands_its_proposals_on(
    loop: PlacementOptLoop,
    config: Config,
    files: dict[str, Path],
    mocker: MockerFixture,
) -> None:
    loop.begin_iteration(config)
    failed = _fake_state(mocker, {"route__drc_errors": 3}, _proposal_views(files))

    loop.end_iteration(failed, False)

    assert loop.next_inputs.config_mem_csv == files["csv_b"]
    assert (loop.last_clean, loop.clean_seen) == (False, False)
    assert loop.winner is None


def test_proposals_repeating_their_inputs_mark_convergence(
    loop: PlacementOptLoop,
    config: Config,
    files: dict[str, Path],
    mocker: MockerFixture,
) -> None:
    loop.next_inputs = IterationInputs(
        files["csv_b"], files["reconnect"], files["order"]
    )
    loop.begin_iteration(config)
    state = _fake_state(
        mocker,
        {"design__die__bbox": "0 0 10 10", "route__wirelength": 1},
        {
            CONFIG_MEM_FORMAT.id: files["csv_b_again"],
            RECONNECT_FORMAT.id: files["reconnect"],
            TILE_INTERFACE_ORDER_FORMAT.id: files["order_again"],
        },
    )

    loop.end_iteration(state, True)

    assert loop.converged is True


def test_the_winner_is_the_smallest_die_then_the_shortest_wirelength(
    loop: PlacementOptLoop, files: dict[str, Path], mocker: MockerFixture
) -> None:
    first = IterationInputs(files["csv_a"], None, None)
    second = IterationInputs(files["csv_b"], files["reconnect"], files["order"])

    loop.applied = first
    assert loop.consider(
        _fake_state(
            mocker, {"design__die__bbox": "0 0 10 10", "route__wirelength": 200}
        )
    )
    assert loop.winner == first

    loop.applied = second
    assert loop.consider(
        _fake_state(
            mocker, {"design__die__bbox": "0 0 10 10", "route__wirelength": 100}
        )
    )
    assert loop.winner == second

    loop.applied = first
    assert not loop.consider(
        _fake_state(mocker, {"design__die__bbox": "0 0 12 12", "route__wirelength": 50})
    )
    assert loop.winner == second


class TestNoOptRouting:
    def test_only_the_final_iteration_routes(
        self, loop: PlacementOptLoop, config: Config
    ) -> None:
        routed = []
        for _ in range(BUDGET):
            loop.begin_iteration(config)
            routed.append(loop.last_routed)

        assert routed == [False, False, True]

    def test_convergence_routes_the_next_iteration(
        self, loop: PlacementOptLoop, config: Config
    ) -> None:
        loop.converged = True

        loop.begin_iteration(config)

        assert loop.last_routed is True

    def test_route_every_iteration_routes_from_the_first(
        self, files: dict[str, Path]
    ) -> None:
        config = _config(files, **{ROUTE_EVERY_ITERATION_VARIABLE.name: True})
        loop = PlacementOptLoop(config, growth_cap=GROWTH_CAP, no_opt=True)

        loop.begin_iteration(config)

        assert loop.last_routed is True

    def test_the_loop_runs_the_budget_then_stops_after_the_routed_iteration(
        self, loop: PlacementOptLoop
    ) -> None:
        loop.iteration, loop.last_routed = 1, False
        assert loop.should_continue() is True
        loop.iteration, loop.last_routed = BUDGET, True
        assert loop.should_continue() is False
        loop.iteration, loop.last_routed = 2, True
        assert loop.should_continue() is False

    def test_route_every_mode_stops_only_on_convergence(
        self, files: dict[str, Path]
    ) -> None:
        config = _config(files, **{ROUTE_EVERY_ITERATION_VARIABLE.name: True})
        loop = PlacementOptLoop(config, growth_cap=GROWTH_CAP, no_opt=True)
        loop.iteration, loop.last_routed = 2, True

        assert loop.should_continue() is True

        loop.converged = True
        assert loop.should_continue() is False


class TestShrinkingBudget:
    @pytest.fixture
    def loop(self, config: Config) -> PlacementOptLoop:
        return PlacementOptLoop(config, growth_cap=GROWTH_CAP, no_opt=False)

    def test_growth_keeps_the_usual_cap_and_the_budget_follows_it(
        self, loop: PlacementOptLoop
    ) -> None:
        loop.iteration = 3
        assert loop.should_continue() is True
        loop.iteration = GROWTH_CAP
        assert loop.should_continue() is False
        loop.clean_seen, loop.since_clean = True, BUDGET - 1
        assert loop.should_continue() is True
        loop.since_clean = BUDGET
        assert loop.should_continue() is False
        assert loop.max_iterations == GROWTH_CAP + BUDGET

    def test_the_budget_is_counted_from_the_first_clean_iteration(
        self, loop: PlacementOptLoop, config: Config, mocker: MockerFixture
    ) -> None:
        loop.begin_iteration(config)
        assert loop.since_clean == 0

        loop.end_iteration(_fake_state(mocker, {}), True)
        loop.begin_iteration(config)

        assert loop.since_clean == 1


def test_the_winners_inputs_are_exported_as_views(
    loop: PlacementOptLoop, files: dict[str, Path], tmp_path: Path
) -> None:
    loop.winner = IterationInputs(files["csv_b"], files["reconnect"], files["order"])
    step_dir = tmp_path / "step"
    step_dir.mkdir()

    views = loop.export_winner(step_dir, "test_design")

    assert set(views) == {CONFIG_MEM_FORMAT, TILE_INTERFACE_ORDER_FORMAT}
    assert Path(views[CONFIG_MEM_FORMAT]).read_text() == CSV_B
    assert (
        Path(views[TILE_INTERFACE_ORDER_FORMAT]).read_text()
        == files["order"].read_text()
    )


def test_a_winner_that_kept_the_default_layout_exports_no_order(
    loop: PlacementOptLoop, files: dict[str, Path], tmp_path: Path
) -> None:
    loop.winner = IterationInputs(files["csv_a"], None, None)
    step_dir = tmp_path / "step"
    step_dir.mkdir()

    views = loop.export_winner(step_dir, "test_design")

    assert set(views) == {CONFIG_MEM_FORMAT}
