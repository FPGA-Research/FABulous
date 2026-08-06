"""Tests for apply_step_substitutions."""

import pytest
from librelane.flows.flow import FlowException
from librelane.steps.step import Step

from fabulous.fabric_generator.gds_generator.steps.step_substitution import (
    apply_step_substitutions,
)


class _StepA(Step):
    id = "Test.A"
    name = "A"
    inputs = []  # noqa: RUF012
    outputs = []  # noqa: RUF012
    config_vars = []  # noqa: RUF012


class _StepB(Step):
    id = "Test.B"
    name = "B"
    inputs = []  # noqa: RUF012
    outputs = []  # noqa: RUF012
    config_vars = []  # noqa: RUF012


class _StepC(Step):
    id = "Test.C"
    name = "C"
    inputs = []  # noqa: RUF012
    outputs = []  # noqa: RUF012
    config_vars = []  # noqa: RUF012


class TestApplyStepSubstitutions:
    """Test suite for apply_step_substitutions."""

    def test_replace(self) -> None:
        """A bare id replaces the matched step in place."""
        result = apply_step_substitutions([_StepA, _StepB], {"Test.A": _StepC})
        assert result == [_StepC, _StepB]

    def test_append(self) -> None:
        """A `+id` inserts the new step immediately after the match."""
        result = apply_step_substitutions([_StepA, _StepB], {"+Test.A": _StepC})
        assert result == [_StepA, _StepC, _StepB]

    def test_prepend(self) -> None:
        """A `-id` inserts the new step immediately before the match."""
        result = apply_step_substitutions([_StepA, _StepB], {"-Test.B": _StepC})
        assert result == [_StepA, _StepC, _StepB]

    def test_remove(self) -> None:
        """A `None` value removes the matched step."""
        result = apply_step_substitutions([_StepA, _StepB], {"Test.A": None})
        assert result == [_StepB]

    def test_glob_match(self) -> None:
        """Substitution ids support fnmatch-style globbing, same as LibreLane."""
        result = apply_step_substitutions([_StepA, _StepB], {"Test.*": None})
        assert result == []

    def test_does_not_mutate_input(self) -> None:
        """The original steps list is left untouched."""
        original = [_StepA, _StepB]
        apply_step_substitutions(original, {"Test.A": _StepC})
        assert original == [_StepA, _StepB]

    def test_list_of_tuples(self) -> None:
        """Substitutions may be given as a list of (id, step) tuples."""
        result = apply_step_substitutions([_StepA, _StepB], [("Test.A", _StepC)])
        assert result == [_StepC, _StepB]

    def test_no_match_raises(self) -> None:
        """Substituting an id with no matching step raises FlowException."""
        with pytest.raises(FlowException):
            apply_step_substitutions([_StepA], {"Test.Nonexistent": _StepC})

    def test_remove_no_match_raises(self) -> None:
        """Removing an id with no matching step raises FlowException."""
        with pytest.raises(FlowException):
            apply_step_substitutions([_StepA], {"Test.Nonexistent": None})

    def test_append_none_raises(self) -> None:
        """Appending/prepending with a None replacement is not a valid operation."""
        with pytest.raises(FlowException):
            apply_step_substitutions([_StepA], {"+Test.A": None})
