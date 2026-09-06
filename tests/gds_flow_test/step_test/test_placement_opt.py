"""Tests for what `PlacementDrivenTileOptimisation` adds to the area optimisation.

The loop body never runs here. The bookkeeping itself is tested against
`PlacementOptLoop` in `opt_test/test_loop.py`; what is left is where the step
meets it: the body it runs, the die it moves to after a clean iteration, the
routing it skips and the views it exports.
"""

# ruff: noqa: SLF001

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
    TILE_INTERFACE_ORDER_FORMAT,
)
from fabulous.fabric_generator.gds_generator.opt.loop import (
    IterationInputs,
    PlacementOptLoop,
)
from fabulous.fabric_generator.gds_generator.opt.placement_opt import (
    PlacementDrivenTileOptimisation,
)
from fabulous.fabric_generator.gds_generator.opt.tile_area_opt import OptMode
from fabulous.fabric_generator.gds_generator.opt.tile_interface import (
    write_interface_order,
)
from fabulous.fabric_generator.gds_generator.opt.variables import (
    CONFIG_MAPPING_VARIABLE,
    CONFIG_MEM_CSV_VARIABLE,
    PLACEMENT_ITERATIONS_VARIABLE,
    ROUTE_EVERY_ITERATION_VARIABLE,
    TILE_INTERFACE_ORDER_VARIABLE,
    TILE_INTERFACE_PAIRS_VARIABLE,
    TILE_INTERFACE_VARIABLE,
)
from fabulous.fabric_generator.gds_generator.steps.apply_config_mapping import (
    ApplyConfigMapping,
)
from fabulous.fabric_generator.gds_generator.steps.dump_placement import DumpPlacement
from fabulous.fabric_generator.gds_generator.steps.propose_config_mapping import (
    ProposeConfigMapping,
)
from fabulous.fabric_generator.gds_generator.steps.propose_tile_interface_order import (
    ProposeTileInterfaceOrder,
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
        "pairs": tmp_path / "T_pin_pairs.yaml",
        "order": tmp_path / "proposal.interface_order.yaml",
    }
    paths["csv_a"].write_text(CSV_A)
    paths["csv_b"].write_text(CSV_B)
    paths["reconnect"].write_text("{}")
    paths["pairs"].write_text("- {axis: vertical, first: N1BEG, second: N1END}\n")
    write_interface_order(ORDER, paths["order"])
    return paths


@pytest.fixture
def opt_step(
    mock_config: Config, files: dict[str, Path], tmp_path: Path, mocker: MockerFixture
) -> PlacementDrivenTileOptimisation:
    mocker.patch(
        "fabulous.fabric_generator.gds_generator.opt.tile_area_opt.get_pitch",
        return_value=(Decimal("0.46"), Decimal("2.72")),
    )
    mocker.patch(
        "fabulous.fabric_generator.gds_generator.opt.tile_area_opt.get_routing_obstructions",
        return_value=[],
    )
    config = mock_config.copy(
        **{
            CONFIG_MAPPING_VARIABLE.name: True,
            TILE_INTERFACE_VARIABLE.name: True,
            PLACEMENT_ITERATIONS_VARIABLE.name: BUDGET,
            ROUTE_EVERY_ITERATION_VARIABLE.name: False,
            CONFIG_MEM_CSV_VARIABLE.name: str(files["csv_a"]),
            TILE_INTERFACE_PAIRS_VARIABLE.name: str(files["pairs"]),
            TILE_INTERFACE_ORDER_VARIABLE.name: None,
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
    step.loop = PlacementOptLoop(
        config, growth_cap=PlacementDrivenTileOptimisation.max_iterations, no_opt=True
    )
    return step


def test_the_optimisation_steps_sit_around_the_loop_body() -> None:
    steps = PlacementDrivenTileOptimisation.Steps
    assert steps[steps.index(OpenROAD.Floorplan) + 1] is ApplyConfigMapping
    cts = steps.index(OpenROAD.CTS)
    assert steps[cts + 1 : cts + 4] == [
        DumpPlacement,
        ProposeConfigMapping,
        ProposeTileInterfaceOrder,
    ]
    assert steps[cts + 4] is OpenROAD.GlobalRouting
    assert CONFIG_MEM_FORMAT in PlacementDrivenTileOptimisation.outputs
    assert TILE_INTERFACE_ORDER_FORMAT in PlacementDrivenTileOptimisation.outputs
    assert PlacementDrivenTileOptimisation.propagate_exceptions == (GDSFlowError,)


def test_run_sizes_the_body_by_the_growth_cap_plus_the_budget(
    opt_step: PlacementDrivenTileOptimisation, mock_state: State, mocker: MockerFixture
) -> None:
    run = mocker.patch(
        "fabulous.fabric_generator.gds_generator.opt.tile_area_opt.WhileStep.run",
        return_value=({}, {}),
    )

    opt_step.run(mock_state)

    assert (
        opt_step.max_iterations
        == PlacementDrivenTileOptimisation.max_iterations + BUDGET
    )
    run.assert_called_once()


def test_the_body_stops_after_the_proposals_when_the_iteration_does_not_route(
    opt_step: PlacementDrivenTileOptimisation, mock_state: State
) -> None:
    propose = ProposeTileInterfaceOrder(opt_step.config)
    opt_step.loop.last_routed = False
    assert opt_step.mid_iteration_break(mock_state, propose) is True
    opt_step.loop.last_routed = True
    assert opt_step.mid_iteration_break(mock_state, propose) is False


class TestBalanceShrink:
    @pytest.fixture
    def balance_step(
        self, opt_step: PlacementDrivenTileOptimisation
    ) -> PlacementDrivenTileOptimisation:
        opt_step.config = opt_step.config.copy(FABULOUS_OPT_MODE=OptMode.BALANCE)
        opt_step.loop = PlacementOptLoop(
            opt_step.config,
            growth_cap=PlacementDrivenTileOptimisation.max_iterations,
            no_opt=False,
        )
        return opt_step

    def test_the_larger_axis_shrinks_after_a_clean_iteration(
        self, balance_step: PlacementDrivenTileOptimisation
    ) -> None:
        balance_step.loop.clean_seen = balance_step.loop.last_clean = True
        assert balance_step._compute_shrunk_dimensions(
            Decimal(100), Decimal(60), Decimal("2.3"), Decimal("2.72")
        ) == (Decimal("97.7"), Decimal(60))

    def test_the_die_holds_after_a_failure_that_follows_a_clean_run(
        self, balance_step: PlacementDrivenTileOptimisation
    ) -> None:
        balance_step.loop.clean_seen, balance_step.loop.last_clean = True, False
        assert balance_step._compute_shrunk_dimensions(
            Decimal(100), Decimal(60), Decimal("2.3"), Decimal("2.72")
        ) == (Decimal(100), Decimal(60))

    def test_the_pin_floor_ends_the_loop(
        self, balance_step: PlacementDrivenTileOptimisation, mock_state: State
    ) -> None:
        balance_step.config = balance_step.config.copy(
            FABULOUS_PIN_MIN_WIDTH=Decimal(99)
        )
        balance_step.loop.clean_seen = balance_step.loop.last_clean = True

        assert balance_step._compute_shrunk_dimensions(
            Decimal(100), Decimal(60), Decimal("2.3"), Decimal("2.72")
        ) == (Decimal(100), Decimal(60))
        assert balance_step.loop.shrink_exhausted is True
        assert balance_step.condition(mock_state) is False

    def test_pre_iteration_shrinks_the_die_once_a_clean_run_exists(
        self,
        balance_step: PlacementDrivenTileOptimisation,
        mock_state: State,
        tmp_path: Path,
    ) -> None:
        balance_step._current_iter_dir = tmp_path / "step" / "iter_2"
        balance_step.loop.clean_seen = balance_step.loop.last_clean = True
        balance_step.last_core_area = Decimal("100.28") * Decimal("65.28")

        balance_step.pre_iteration_callback(mock_state)

        _, _, width, height = balance_step.config["DIE_AREA"]
        assert (width, height) == (Decimal("97.98"), Decimal("65.28"))


def test_post_loop_exports_the_winners_inputs_as_views(
    opt_step: PlacementDrivenTileOptimisation, files: dict[str, Path], mock_state: State
) -> None:
    opt_step.last_working_state = State(
        metrics={**mock_state.metrics, "design__die__bbox": "0 0 10 10"}
    )
    opt_step.loop.winner = IterationInputs(
        files["csv_b"], files["reconnect"], files["order"]
    )

    result = opt_step.post_loop_callback(mock_state)

    csv_out = Path(opt_step.step_dir) / "test_design.ConfigMem.csv"
    order_out = Path(opt_step.step_dir) / "test_design.interface_order.yaml"
    assert str(result[CONFIG_MEM_FORMAT]) == str(csv_out)
    assert csv_out.read_text() == CSV_B
    assert str(result[TILE_INTERFACE_ORDER_FORMAT]) == str(order_out)
    assert order_out.read_text() == files["order"].read_text()
    assert result.metrics["fabulous__clean_probes"] == []


def test_post_loop_exports_no_order_when_the_winner_kept_the_default_layout(
    opt_step: PlacementDrivenTileOptimisation, files: dict[str, Path], mock_state: State
) -> None:
    opt_step.last_working_state = State(
        metrics={**mock_state.metrics, "design__die__bbox": "0 0 10 10"}
    )
    opt_step.loop.winner = IterationInputs(files["csv_a"], None, None)

    result = opt_step.post_loop_callback(mock_state)

    assert str(result[CONFIG_MEM_FORMAT]).endswith("test_design.ConfigMem.csv")
    assert result.get(TILE_INTERFACE_ORDER_FORMAT) is None
