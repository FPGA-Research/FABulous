"""Tests for the FABulousMacroPlacement step and the placement maths it uses."""

import logging
from decimal import Decimal
from pathlib import Path
from unittest.mock import MagicMock

import pytest
from librelane.config.config import Config
from librelane.config.variable import Instance, Macro, Orientation
from librelane.state.state import State
from librelane.steps.step import StepException
from pytest_mock import MockerFixture

from fabulous.fabric_generator.gds_generator.steps.macro_placement import (
    FABulousMacroPlacement,
    MacroBox,
    MacroPlacementMode,
    find_overlapping_pair,
    oriented_footprint,
    read_macro_size,
    relocate_macro,
)

# The BRAM tile from the issue that motivated the feature: a 1500x2000 die
# holding a 703.02x737.94 SRAM macro centred at (398.49, 631.03), which tile
# area optimisation then grows to 1600x2100.
MACRO_SIZE = (Decimal("703.02"), Decimal("737.94"))
CENTRED_LOCATION = (Decimal("398.49"), Decimal("631.03"))
REFERENCE_EXTENT = (Decimal(1500), Decimal(2000))
LIVE_EXTENT = (Decimal(1600), Decimal(2100))
REFERENCE_DIE_AREA = (Decimal(0), Decimal(0), *REFERENCE_EXTENT)
LIVE_DIE_AREA = (Decimal(0), Decimal(0), *LIVE_EXTENT)


def place(
    mode: MacroPlacementMode,
    location: tuple[Decimal, Decimal],
    live_die: tuple[Decimal, Decimal],
    reference_die: tuple[Decimal, Decimal] | None = REFERENCE_EXTENT,
) -> tuple[Decimal, Decimal]:
    """Relocate the issue's SRAM macro, defaulting the unchanging arguments."""
    return relocate_macro("u_sram", mode, location, MACRO_SIZE, live_die, reference_die)


class TestReadMacroSize:
    """Macro geometry comes from the LEF, read by KLayout."""

    def test_reads_the_declared_size(self, macro_lef: Path) -> None:
        """The outline layer yields the declared SIZE, not the drawn extent."""
        assert read_macro_size([macro_lef], "sram") == MACRO_SIZE

    def test_rejects_a_module_absent_from_the_lef(self, macro_lef: Path) -> None:
        """A module name that matches no MACRO is an actionable error."""
        with pytest.raises(ValueError, match="No outline for macro absent"):
            read_macro_size([macro_lef], "absent")


class TestOrientedFootprint:
    """A rotated macro occupies a transposed footprint."""

    @pytest.mark.parametrize(
        "orientation", [Orientation.N, Orientation.S, Orientation.FN, Orientation.FS]
    )
    def test_upright_orientations_keep_the_size(self, orientation: Orientation) -> None:
        """Flips and 180 degree rotations leave the extents alone."""
        assert oriented_footprint(MACRO_SIZE, orientation) == MACRO_SIZE

    @pytest.mark.parametrize(
        "orientation", [Orientation.W, Orientation.E, Orientation.FW, Orientation.FE]
    )
    def test_quarter_turns_transpose_the_size(self, orientation: Orientation) -> None:
        """The 90 degree orientations swap width and height."""
        assert oriented_footprint(MACRO_SIZE, orientation) == (
            MACRO_SIZE[1],
            MACRO_SIZE[0],
        )


class TestMacroPlacementMode:
    """Mode parsing from user-facing config strings."""

    @pytest.mark.parametrize(
        ("value", "expected"),
        [
            ("fix", MacroPlacementMode.FIX),
            ("FIX", MacroPlacementMode.FIX),
            ("Relative", MacroPlacementMode.RELATIVE),
            ("centre", MacroPlacementMode.CENTRE),
            ("CENTER", MacroPlacementMode.CENTRE),
        ],
    )
    def test_parses_case_insensitively(
        self, value: str, expected: MacroPlacementMode
    ) -> None:
        """Both spellings of centre, in any case, resolve to a member."""
        assert MacroPlacementMode(value) is expected

    def test_unknown_mode_warns_and_falls_back_to_fix(
        self, caplog: pytest.LogCaptureFixture
    ) -> None:
        """An unknown mode keeps today's behaviour, but says so."""
        with caplog.at_level(logging.WARNING):
            assert MacroPlacementMode("auto") is MacroPlacementMode.FIX

        assert "fix, relative, centre" in caplog.text
        assert "falling back to fix" in caplog.text


class TestFixMode:
    """`fix` reproduces today's behaviour exactly."""

    def test_location_is_untouched_when_die_grows(self) -> None:
        """The configured location survives a die change verbatim."""
        assert (
            place(MacroPlacementMode.FIX, CENTRED_LOCATION, LIVE_EXTENT)
            == CENTRED_LOCATION
        )

    def test_needs_no_reference_die(self) -> None:
        """`fix` never consults the reference area."""
        assert (
            place(
                MacroPlacementMode.FIX,
                CENTRED_LOCATION,
                LIVE_EXTENT,
                reference_die=None,
            )
            == CENTRED_LOCATION
        )


class TestCentreMode:
    """`centre` ignores the configured location."""

    def test_centres_in_the_live_die(self) -> None:
        """The macro lands on the die centre regardless of its input location."""
        x, y = place(
            MacroPlacementMode.CENTRE,
            (Decimal(0), Decimal(0)),
            LIVE_EXTENT,
            reference_die=None,
        )
        assert x == (LIVE_EXTENT[0] - MACRO_SIZE[0]) / 2
        assert y == (LIVE_EXTENT[1] - MACRO_SIZE[1]) / 2

    def test_rejects_macro_larger_than_the_die(self) -> None:
        """A macro that cannot fit is an error, not a negative origin."""
        with pytest.raises(ValueError, match="u_sram.*does not fit"):
            place(
                MacroPlacementMode.CENTRE,
                CENTRED_LOCATION,
                (Decimal(500), Decimal(2100)),
                reference_die=None,
            )


class TestRelativeMode:
    """`relative` splits the die growth across the macro's free margins."""

    def test_centred_macro_stays_centred(self) -> None:
        """The motivating case: a centred SRAM tracks the growing die centre."""
        x, y = place(MacroPlacementMode.RELATIVE, CENTRED_LOCATION, LIVE_EXTENT)
        assert x == pytest.approx(
            Decimal((LIVE_EXTENT[0] - MACRO_SIZE[0]) / 2), abs=0.01
        )
        assert y == pytest.approx(
            Decimal((LIVE_EXTENT[1] - MACRO_SIZE[1]) / 2), abs=0.01
        )

    def test_edge_hugging_macro_stays_near_the_edge(self) -> None:
        """An off-centre macro keeps its whitespace ratio instead of drifting."""
        location = (Decimal(100), Decimal("631.03"))
        x, _ = place(
            MacroPlacementMode.RELATIVE, location, (Decimal(1600), Decimal(2000))
        )
        # left=100, right=696.98, growth=100 -> 100 + 100 * 100/796.98
        assert x == pytest.approx(Decimal("112.55"), abs=0.01)

    def test_shrinking_die_pulls_the_macro_back(self) -> None:
        """Negative growth is handled by the same proportional split."""
        location = (Decimal(100), Decimal("631.03"))
        x, _ = place(
            MacroPlacementMode.RELATIVE, location, (Decimal(1400), Decimal(2000))
        )
        assert x == pytest.approx(Decimal("87.45"), abs=0.01)

    def test_requires_a_reference_die(self) -> None:
        """Without a reference area the original margins are unknowable."""
        with pytest.raises(ValueError, match="reference"):
            place(
                MacroPlacementMode.RELATIVE,
                CENTRED_LOCATION,
                LIVE_EXTENT,
                reference_die=None,
            )

    def test_rejects_macro_filling_the_reference_axis(self) -> None:
        """With no free margin there is nothing to split the growth across."""
        with pytest.raises(ValueError, match="no free margin"):
            relocate_macro(
                "u_sram",
                MacroPlacementMode.RELATIVE,
                (Decimal(0), Decimal(0)),
                REFERENCE_EXTENT,
                LIVE_EXTENT,
                REFERENCE_EXTENT,
            )

    def test_rejects_location_outside_the_reference_die(self) -> None:
        """A macro hanging off the reference die has a negative margin."""
        with pytest.raises(ValueError, match="outside the reference"):
            place(
                MacroPlacementMode.RELATIVE,
                (Decimal(1400), Decimal("631.03")),
                LIVE_EXTENT,
            )


class TestFindOverlappingPair:
    """Overlap detection guards against illegal floorplans."""

    def test_returns_none_for_disjoint_macros(self) -> None:
        """Side-by-side macros are legal."""
        boxes = [
            MacroBox("a", Decimal(0), Decimal(0), Decimal(100), Decimal(100)),
            MacroBox("b", Decimal(200), Decimal(0), Decimal(100), Decimal(100)),
        ]
        assert find_overlapping_pair(boxes) is None

    def test_abutting_macros_do_not_overlap(self) -> None:
        """Touching edges share no area, so abutment is allowed."""
        boxes = [
            MacroBox("a", Decimal(0), Decimal(0), Decimal(100), Decimal(100)),
            MacroBox("b", Decimal(100), Decimal(0), Decimal(100), Decimal(100)),
        ]
        assert find_overlapping_pair(boxes) is None

    def test_detects_overlapping_macros(self) -> None:
        """Two macros sharing area are reported as a pair."""
        boxes = [
            MacroBox("a", Decimal(0), Decimal(0), Decimal(100), Decimal(100)),
            MacroBox("b", Decimal(50), Decimal(50), Decimal(100), Decimal(100)),
        ]
        pair = find_overlapping_pair(boxes)
        assert pair is not None
        assert {pair[0].instance, pair[1].instance} == {"a", "b"}

    def test_single_macro_never_overlaps(self) -> None:
        """The common single-macro tile short-circuits cleanly."""
        boxes = [MacroBox("a", Decimal(0), Decimal(0), Decimal(100), Decimal(100))]
        assert find_overlapping_pair(boxes) is None


@pytest.fixture
def odbpy_run(mocker: MockerFixture) -> MagicMock:
    """Stub the odbpy invocation so only the emitted config is under test."""
    return mocker.patch("librelane.steps.odb.OdbpyStep.run", return_value=({}, {}))


@pytest.fixture
def librelane_run(mocker: MockerFixture) -> MagicMock:
    """Stub librelane's own macro placement run."""
    return mocker.patch(
        "librelane.steps.odb.ManualMacroPlacement.run", return_value=({}, {})
    )


def make_step(config: Config, state: State, step_dir: Path) -> FABulousMacroPlacement:
    """Build a step whose config and step directory are pinned."""
    step = FABulousMacroPlacement(config, state)
    step.config = config
    step.step_dir = str(step_dir)
    return step


def macros(
    lef: Path,
    instances: dict[str, Instance],
) -> dict[str, Macro]:
    """Build a MACROS mapping backed by the SRAM LEF fixture."""
    return {"sram": Macro(gds=[Path("sram.gds")], lef=[lef], instances=instances)}


def instance(
    location: tuple[Decimal, Decimal] | None,
    orientation: Orientation = Orientation.N,
) -> Instance:
    """Build a macro instance."""
    return Instance(location=location, orientation=orientation)


class TestDelegation:
    """Cases that are librelane's job, not ours."""

    def test_fix_uses_librelane_config_emission(
        self,
        mock_config: Config,
        mock_state: State,
        tmp_path: Path,
        macro_lef: Path,
        librelane_run: MagicMock,
    ) -> None:
        """`fix` replays configured locations, exactly what librelane emits."""
        config = mock_config.copy(
            DIE_AREA=LIVE_DIE_AREA, MACROS=macros(macro_lef, {"u_sram": instance(None)})
        )
        make_step(config, mock_state, tmp_path).run(mock_state)

        librelane_run.assert_called_once()

    def test_no_macros_delegates(
        self,
        mock_config: Config,
        mock_state: State,
        tmp_path: Path,
        librelane_run: MagicMock,
    ) -> None:
        """A tile without macros needs no placement config of ours."""
        config = mock_config.copy(
            DIE_AREA=LIVE_DIE_AREA, FABULOUS_MACRO_PLACEMENT_MODE="centre"
        )
        make_step(config, mock_state, tmp_path).run(mock_state)

        librelane_run.assert_called_once()

    def test_explicit_placement_cfg_wins(
        self,
        mock_config: Config,
        mock_state: State,
        tmp_path: Path,
        macro_lef: Path,
        librelane_run: MagicMock,
    ) -> None:
        """An explicit MACRO_PLACEMENT_CFG stays the source of the locations."""
        cfg = tmp_path / "manual.cfg"
        cfg.write_text("u_sram 10 20 N\n")
        config = mock_config.copy(
            DIE_AREA=LIVE_DIE_AREA,
            FABULOUS_MACRO_PLACEMENT_MODE="centre",
            MACRO_PLACEMENT_CFG=cfg,
            MACROS=macros(macro_lef, {"u_sram": instance(None)}),
        )
        make_step(config, mock_state, tmp_path).run(mock_state)

        librelane_run.assert_called_once()


class TestDerivedPlacement:
    """The config we hand to librelane's placer."""

    def test_centre_ignores_the_configured_location(
        self,
        mock_config: Config,
        mock_state: State,
        tmp_path: Path,
        macro_lef: Path,
        odbpy_run: MagicMock,
    ) -> None:
        """`centre` derives the origin from the live die, location or not."""
        config = mock_config.copy(
            DIE_AREA=LIVE_DIE_AREA,
            FABULOUS_MACRO_PLACEMENT_MODE="centre",
            MACROS=macros(macro_lef, {"u_sram": instance(None)}),
        )
        make_step(config, mock_state, tmp_path).run(mock_state)

        odbpy_run.assert_called_once()
        assert (tmp_path / "placement.cfg").read_text() == "u_sram 448.490 681.030 N\n"

    @pytest.mark.usefixtures("odbpy_run")
    def test_centre_accounts_for_a_rotated_macro(
        self,
        mock_config: Config,
        mock_state: State,
        tmp_path: Path,
        macro_lef: Path,
    ) -> None:
        """A quarter-turned macro is centred on its transposed footprint."""
        config = mock_config.copy(
            DIE_AREA=LIVE_DIE_AREA,
            FABULOUS_MACRO_PLACEMENT_MODE="centre",
            MACROS=macros(macro_lef, {"u_sram": instance(None, Orientation.W)}),
        )
        make_step(config, mock_state, tmp_path).run(mock_state)

        # 703.02x737.94 placed at W occupies 737.94x703.02.
        assert (tmp_path / "placement.cfg").read_text() == "u_sram 431.030 698.490 W\n"

    @pytest.mark.usefixtures("odbpy_run")
    def test_relative_tracks_the_grown_die(
        self,
        mock_config: Config,
        mock_state: State,
        tmp_path: Path,
        macro_lef: Path,
    ) -> None:
        """A macro centred in the authored die stays centred in the grown one."""
        config = mock_config.copy(
            DIE_AREA=LIVE_DIE_AREA,
            FABULOUS_MACRO_PLACEMENT_MODE="relative",
            FABULOUS_MACRO_REFERENCE_DIE_AREA=REFERENCE_DIE_AREA,
            MACROS=macros(macro_lef, {"u_sram": instance(CENTRED_LOCATION)}),
        )
        make_step(config, mock_state, tmp_path).run(mock_state)

        name, x, y, orientation = (tmp_path / "placement.cfg").read_text().split()
        assert name == "u_sram"
        assert orientation == "N"
        assert Decimal(x) == pytest.approx(Decimal("448.49"), abs=0.01)
        assert Decimal(y) == pytest.approx(Decimal("681.03"), abs=0.01)


class TestRejections:
    """Configurations that must fail rather than mis-place."""

    def test_relative_without_a_reference_die_area(
        self,
        mock_config: Config,
        mock_state: State,
        tmp_path: Path,
        macro_lef: Path,
    ) -> None:
        """A missing reference area names both remedies."""
        config = mock_config.copy(
            DIE_AREA=LIVE_DIE_AREA,
            FABULOUS_MACRO_PLACEMENT_MODE="relative",
            MACROS=macros(macro_lef, {"u_sram": instance(CENTRED_LOCATION)}),
        )
        with pytest.raises(StepException, match="DIE_AREA.*centre mode"):
            make_step(config, mock_state, tmp_path).run(mock_state)

    def test_relative_without_an_instance_location(
        self,
        mock_config: Config,
        mock_state: State,
        tmp_path: Path,
        macro_lef: Path,
    ) -> None:
        """Without a location there are no original margins to preserve."""
        config = mock_config.copy(
            DIE_AREA=LIVE_DIE_AREA,
            FABULOUS_MACRO_PLACEMENT_MODE="relative",
            FABULOUS_MACRO_REFERENCE_DIE_AREA=REFERENCE_DIE_AREA,
            MACROS=macros(macro_lef, {"u_sram": instance(None)}),
        )
        with pytest.raises(StepException, match="has no location"):
            make_step(config, mock_state, tmp_path).run(mock_state)

    def test_overlapping_macros(
        self,
        mock_config: Config,
        mock_state: State,
        tmp_path: Path,
        macro_lef: Path,
    ) -> None:
        """Two macros sharing area fail rather than reaching the floorplan."""
        config = mock_config.copy(
            DIE_AREA=LIVE_DIE_AREA,
            FABULOUS_MACRO_PLACEMENT_MODE="relative",
            FABULOUS_MACRO_REFERENCE_DIE_AREA=REFERENCE_DIE_AREA,
            MACROS=macros(
                macro_lef,
                {
                    "u_a": instance((Decimal(0), Decimal(0))),
                    "u_b": instance((Decimal(100), Decimal(100))),
                },
            ),
        )
        with pytest.raises(StepException, match="u_a and u_b overlap"):
            make_step(config, mock_state, tmp_path).run(mock_state)

    def test_unknown_mode_places_as_fix(
        self,
        mock_config: Config,
        mock_state: State,
        tmp_path: Path,
        macro_lef: Path,
        librelane_run: MagicMock,
    ) -> None:
        """An unsupported mode degrades to fix rather than stopping the flow."""
        config = mock_config.copy(
            DIE_AREA=LIVE_DIE_AREA,
            FABULOUS_MACRO_PLACEMENT_MODE="auto",
            MACROS=macros(macro_lef, {"u_sram": instance(CENTRED_LOCATION)}),
        )
        make_step(config, mock_state, tmp_path).run(mock_state)

        librelane_run.assert_called_once()
