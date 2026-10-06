"""Tests for WhileStep base class."""

import pytest
from librelane.common import GenericDict
from librelane.config.config import Config
from librelane.config.variable import Variable
from librelane.state.state import State
from librelane.steps.step import Step
from pytest_mock import MockerFixture

from fabulous.fabric_generator.gds_generator.steps.tile_area_opt import (
    TileAreaOptimisation,
)
from fabulous.fabric_generator.gds_generator.steps.while_step import (
    _SUBSTITUTE_STEPS_VAR,
    WhileStep,
)

_RUN_INNER_VAR = Variable("TEST_RUN_INNER", bool, "Gates Test.Inner.", default=True)


class CustomError(Exception):
    """Marker exception used to exercise propagate_exceptions handling."""


class _InnerStep(Step):
    """Minimal sub-step whose ``start`` is patched per-test."""

    id = "Test.Inner"
    name = "Inner"
    inputs = []  # noqa: RUF012
    outputs = []  # noqa: RUF012
    config_vars = []  # noqa: RUF012

    def run(self, state_in: State, **kwargs: dict) -> tuple[dict, dict]:  # noqa: D102, ARG002
        return {}, {}


class _ReplacementStep(Step):
    """Marker sub-step used to verify config-driven step substitution."""

    id = "Test.Replacement"
    name = "Replacement"
    inputs = []  # noqa: RUF012
    outputs = []  # noqa: RUF012
    config_vars = []  # noqa: RUF012

    def run(self, state_in: State, **kwargs: dict) -> tuple[dict, dict]:  # noqa: D102, ARG002
        return {}, {}


class TestWhileStep:
    """Test suite for WhileStep base class."""

    def test_condition_default(self, mock_config: Config, mock_state: State) -> None:
        """Test that condition returns True by default.

        Also validates that default class attributes are set correctly, as they affect
        the condition behavior.
        """
        step = WhileStep(mock_config)

        # Verify default class attributes are set (tests actual behavior dependency)
        assert WhileStep.max_iterations == 10, "max_iterations should default to 10"
        assert WhileStep.raise_on_failure is True, (
            "raise_on_failure should default to True"
        )
        assert WhileStep.break_on_failure is True, (
            "break_on_failure should default to True"
        )

        # Test the actual condition behavior
        assert step.condition(mock_state) is True

    def test_mid_iteration_break_default(
        self, mock_config: Config, mock_state: State, mocker: MockerFixture
    ) -> None:
        """Test that mid_iteration_break returns False by default."""
        mock_step_class = mocker.MagicMock()
        step = WhileStep(mock_config)
        assert step.mid_iteration_break(mock_state, mock_step_class) is False

    def test_post_loop_callback_default(
        self, mock_config: Config, mock_state: State
    ) -> None:
        """Test that post_loop_callback returns state unchanged by default."""
        step = WhileStep(mock_config)
        result = step.post_loop_callback(mock_state)
        assert result == mock_state

    def test_pre_iteration_callback_default(
        self, mock_config: Config, mock_state: State
    ) -> None:
        """Test that pre_iteration_callback returns state unchanged by default."""
        step = WhileStep(mock_config)
        result = step.pre_iteration_callback(mock_state)
        assert result == mock_state

    def test_post_iteration_callback_default(
        self, mock_config: Config, mock_state: State
    ) -> None:
        """Test that post_iteration_callback returns state unchanged by default."""
        step = WhileStep(mock_config)
        result = step.post_iteration_callback(mock_state, True)
        assert result == mock_state

    def test_get_current_iteration_dir_none_initially(
        self, mock_config: Config
    ) -> None:
        """Test that current iteration directory is None initially."""
        step = WhileStep(mock_config)
        assert step.get_current_iteration_dir() is None

    def test_propagate_exceptions_reraises_over_break(
        self,
        mock_config: Config,
        mock_state: State,
        mocker: MockerFixture,
        tmp_path,  # noqa: ANN001
    ) -> None:
        """An exception in propagate_exceptions re-raises even when break_on_failure.

        propagate_exceptions must win over break_on_failure (and raise_on_failure
        being False), which would otherwise swallow the error via ``break``.
        """

        class PropagatingWhileStep(WhileStep):
            Steps = [_InnerStep]  # noqa: RUF012
            outputs = []  # noqa: RUF012
            propagate_exceptions = (CustomError,)
            raise_on_failure = False
            break_on_failure = True
            max_iterations = 1

        mocker.patch.object(_InnerStep, "start", side_effect=CustomError("boom"))

        step = PropagatingWhileStep(mock_config)
        step.config = mock_config
        step.step_dir = str(tmp_path)
        step.toolbox = mocker.MagicMock()
        step.name = "PropagatingWhileStep"

        with pytest.raises(CustomError):
            step.run(mock_state)

    def test_break_on_failure_swallows_when_not_propagated(
        self,
        mock_config: Config,
        mock_state: State,
        mocker: MockerFixture,
        tmp_path,  # noqa: ANN001
    ) -> None:
        """With empty propagate_exceptions, break_on_failure swallows the error."""

        class SwallowingWhileStep(WhileStep):
            Steps = [_InnerStep]  # noqa: RUF012
            outputs = []  # noqa: RUF012
            propagate_exceptions = ()
            raise_on_failure = False
            break_on_failure = True
            max_iterations = 1

        mocker.patch.object(_InnerStep, "start", side_effect=CustomError("boom"))

        step = SwallowingWhileStep(mock_config)
        step.config = mock_config
        step.step_dir = str(tmp_path)
        step.toolbox = mocker.MagicMock()
        step.name = "SwallowingWhileStep"

        # Should complete without raising because break_on_failure breaks the loop.
        views_update, metrics_update = step.run(mock_state)
        assert views_update == {}
        assert metrics_update == {}

    def test_substitute_steps_replaces_loop_body_step(
        self,
        mock_config: Config,
        mock_state: State,
        mocker: MockerFixture,
        tmp_path,  # noqa: ANN001
    ) -> None:
        """FABULOUS_LOOP_SUBSTITUTE_STEPS swaps a step inside the loop body.

        Config-driven substitution reaches WhileStep's internal Steps list, the
        gap LibreLane's meta.substituting_steps cannot cross since it only
        walks a flow's top-level Steps.
        """

        class SubstitutableWhileStep(WhileStep):
            Steps = [_InnerStep]  # noqa: RUF012
            outputs = []  # noqa: RUF012
            max_iterations = 1

        config = Config(
            dict(
                mock_config,
                FABULOUS_LOOP_SUBSTITUTE_STEPS={"Test.Inner": _ReplacementStep},
            )
        )
        inner_start = mocker.patch.object(_InnerStep, "start")
        replacement_start = mocker.patch.object(
            _ReplacementStep, "start", return_value=mock_state
        )

        mocker.patch.object(Config, "dumps", return_value="{}")
        mocker.patch("pathlib.Path.write_text")

        step = SubstitutableWhileStep(config)
        step.config = config
        step.step_dir = str(tmp_path)
        step.toolbox = mocker.MagicMock()
        step.name = "SubstitutableWhileStep"

        step.run(mock_state)

        inner_start.assert_not_called()
        replacement_start.assert_called_once()

    @pytest.mark.parametrize(
        "payload",
        [
            pytest.param({"Test.Inner": "Test.Replacement"}, id="replace"),
            pytest.param({"+Test.Inner": "Test.Replacement"}, id="append"),
            pytest.param({"-Test.Inner": "Test.Replacement"}, id="prepend"),
            pytest.param({"Test.Inner": None}, id="remove"),
            pytest.param(None, id="unset"),
        ],
    )
    def test_substitute_steps_var_compiles(self, payload: dict | None) -> None:
        """Test that every documented substitution payload survives compilation.

        The test above builds ``Config(dict(...))`` directly, bypassing
        ``Variable.compile``, so it passes for any declared type.
        """
        _, final = _SUBSTITUTE_STEPS_VAR.compile(
            GenericDict({_SUBSTITUTE_STEPS_VAR.name: payload}),
            warning_list_ref=[],
        )
        assert final == payload


class TestWhileStepGating:
    """Loop-body steps honour `gating_config_vars` like a SequentialFlow."""

    @pytest.mark.parametrize(
        ("run_inner", "expected_starts"),
        [
            pytest.param(True, 1, id="enabled"),
            pytest.param(False, 0, id="disabled"),
        ],
    )
    def test_gated_step_runs_only_when_enabled(
        self,
        mock_config: Config,
        mock_state: State,
        mocker: MockerFixture,
        tmp_path,  # noqa: ANN001
        run_inner: bool,
        expected_starts: int,
    ) -> None:
        """A loop-body step whose gating variable is False is skipped."""

        class GatedWhileStep(WhileStep):
            Steps = [_InnerStep]  # noqa: RUF012
            outputs = []  # noqa: RUF012
            config_vars = [_RUN_INNER_VAR]  # noqa: RUF012
            gating_config_vars = {"Test.Inner": ["TEST_RUN_INNER"]}  # noqa: RUF012
            max_iterations = 1

        config = Config(dict(mock_config, TEST_RUN_INNER=run_inner))
        inner_start = mocker.patch.object(_InnerStep, "start", return_value=mock_state)
        mocker.patch.object(Config, "dumps", return_value="{}")
        mocker.patch("pathlib.Path.write_text")

        step = GatedWhileStep(config)
        step.config = config
        step.step_dir = str(tmp_path)
        step.toolbox = mocker.MagicMock()
        step.name = "GatedWhileStep"

        step.run(mock_state)

        assert inner_start.call_count == expected_starts

    @pytest.mark.parametrize(
        ("config_vars", "gating", "message"),
        [
            pytest.param(
                [],
                {"Test.Inner": ["TEST_RUN_INNER"]},
                "Gating variable 'TEST_RUN_INNER' for step 'Test.Inner' is not in "
                "the config_vars",
                id="undeclared_variable",
            ),
            pytest.param(
                [Variable("TEST_RUN_INNER", int, "Not a bool.", default=1)],
                {"Test.Inner": ["TEST_RUN_INNER"]},
                "Gating variable 'TEST_RUN_INNER' in '.*' is not a bool",
                id="non_bool_variable",
            ),
            pytest.param(
                [_RUN_INNER_VAR],
                {"Test.Missing": ["TEST_RUN_INNER"]},
                "Gated step 'Test.Missing' is not in the Steps",
                id="unknown_step",
            ),
        ],
    )
    def test_invalid_gating_is_rejected_at_class_creation(
        self,
        config_vars: list[Variable],
        gating: dict[str, list[str]],
        message: str,
    ) -> None:
        """A gating entry that could never be honoured fails when the class is made."""
        bad_config_vars = config_vars
        bad_gating = gating
        with pytest.raises(TypeError, match=message):

            class _BadGating(WhileStep):
                Steps = [_InnerStep]  # noqa: RUF012
                outputs = []  # noqa: RUF012
                config_vars = bad_config_vars
                gating_config_vars = bad_gating

    def test_tile_area_optimisation_declares_its_gating_variables(self) -> None:
        """The gating variables survive the step's config filtering."""
        declared = {variable.name for variable in TileAreaOptimisation.config_vars}
        gating_names = {
            name
            for names in TileAreaOptimisation.gating_config_vars.values()
            for name in names
        }

        assert TileAreaOptimisation.gating_config_vars == {
            "OpenROAD.TapEndcapInsertion": ["RUN_TAP_ENDCAP_INSERTION"],
            "OpenROAD.CTS": ["RUN_CTS"],
            "OpenROAD.RepairAntennas": ["RUN_ANTENNA_REPAIR"],
        }
        assert gating_names <= declared
