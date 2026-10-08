"""Tests for FABulousFabricMacroFlow - Fabric stitching flow.

Tests focus on:
- Die area computation
- Macro overlap validation
- Tile size validation
- Row and column size computation
- Spacing variable types and step substitutions
"""

# ruff: noqa: SLF001

from decimal import Decimal
from typing import TYPE_CHECKING, Any
from unittest.mock import MagicMock

import pytest
from conftest import create_instance, create_macro
from librelane.config.variable import Instance, Macro, Orientation
from pytest_mock import MockerFixture

from fabulous.fabric_definition.tile import Tile
from fabulous.fabric_generator.gds_generator.flows.fabric_macro_flow import (
    FABulousFabricMacroFlow,
    FABulousFabricVHDLMacroFlow,
    configs,
)
from fabulous.fabric_generator.gds_generator.flows.flow_define import physical_steps
from fabulous.fabric_generator.gds_generator.steps.fabric_IO_placement import (
    FABulousFabricIOPlacement,
)
from fabulous.fabric_generator.gds_generator.steps.odb_connect_pdn import FABulousPDN
from tests.conftest import make_empty_tile, make_fabric_from_grid

if TYPE_CHECKING:
    from fabulous.fabric_definition.fabric import Fabric


def _tile(name: str) -> Tile:
    return make_empty_tile(name, pinOrderConfig={})


class TestComputeDieArea:
    """Tests for _compute_die_area method."""

    @pytest.fixture
    def flow(self, mocker: MockerFixture) -> MagicMock:
        """Create a mock flow with _compute_die_area method bound."""
        mock_flow: MagicMock = mocker.MagicMock(spec=FABulousFabricMacroFlow)
        mock_flow._compute_die_area = FABulousFabricMacroFlow._compute_die_area
        return mock_flow

    @pytest.mark.parametrize(
        ("row_heights", "column_widths", "halo", "spacing", "expected"),
        [
            pytest.param(
                [Decimal(100), Decimal(200)],
                [Decimal(150), Decimal(250)],
                (Decimal(0), Decimal(0), Decimal(0), Decimal(0)),
                (Decimal(0), Decimal(0)),
                (Decimal(400), Decimal(300)),
                id="no_spacing",
            ),
            # width = left + right + 200 = 10 + 30 + 200
            # height = bottom + top + 100 = 20 + 40 + 100
            pytest.param(
                [Decimal(100)],
                [Decimal(200)],
                (Decimal(10), Decimal(20), Decimal(30), Decimal(40)),
                (Decimal(0), Decimal(0)),
                (Decimal(240), Decimal(160)),
                id="halo_spacing",
            ),
            # Width adds one 5 gap between 2 columns, height two 10 gaps.
            pytest.param(
                [Decimal(100), Decimal(100), Decimal(100)],
                [Decimal(200), Decimal(200)],
                (Decimal(0), Decimal(0), Decimal(0), Decimal(0)),
                (Decimal(5), Decimal(10)),
                (Decimal(405), Decimal(320)),
                id="tile_spacing",
            ),
            pytest.param(
                [],
                [],
                (Decimal(10), Decimal(10), Decimal(10), Decimal(10)),
                (Decimal(5), Decimal(5)),
                (Decimal(20), Decimal(20)),
                id="empty_grid_is_halo_only",
            ),
        ],
    )
    def test_compute_die_area(
        self,
        flow: MagicMock,
        row_heights: list[Decimal],
        column_widths: list[Decimal],
        halo: tuple[Decimal, Decimal, Decimal, Decimal],
        spacing: tuple[Decimal, Decimal],
        expected: tuple[Decimal, Decimal],
    ) -> None:
        """Die size is the summed rows/columns plus halo and inter-tile spacing."""
        assert (
            flow._compute_die_area(flow, row_heights, column_widths, halo, spacing)
            == expected
        )


class TestValidateNoMacroOverlaps:
    """Tests for _validate_no_macro_overlaps method.

    Every tile is 100 x 100; a placement is `(tile, instance, x, y)`.
    """

    @pytest.fixture
    def flow(self, mocker: MockerFixture) -> MagicMock:
        """Create a mock flow with _validate_no_macro_overlaps method bound."""
        mock_flow: MagicMock = mocker.MagicMock(spec=FABulousFabricMacroFlow)
        mock_flow._validate_no_macro_overlaps = (
            FABulousFabricMacroFlow._validate_no_macro_overlaps
        )
        return mock_flow

    @staticmethod
    def _macros(placements: list[tuple[str, str, int, int]]) -> dict[str, Macro]:
        instances: dict[str, dict[str, Instance]] = {}
        for tile, instance, x, y in placements:
            instances.setdefault(tile, {})[instance] = create_instance(
                Decimal(x), Decimal(y)
            )
        return {tile: create_macro(insts) for tile, insts in instances.items()}

    @pytest.mark.parametrize(
        "placements",
        [
            pytest.param([], id="empty"),
            pytest.param([("t1", "i1", 0, 0)], id="single"),
            pytest.param([("t1", "i1", 0, 0), ("t2", "i2", 200, 0)], id="apart"),
            pytest.param([("t1", "i1", 0, 0), ("t2", "i2", 100, 0)], id="x_touching"),
            pytest.param([("t1", "i1", 0, 0), ("t2", "i2", 0, 100)], id="y_touching"),
            pytest.param(
                [("t1", "i1", 0, 0), ("t2", "i2", 200, 50)], id="y_overlap_only"
            ),
            pytest.param(
                [("t1", "i1", 0, 0), ("t2", "i2", 50, 200)], id="x_overlap_only"
            ),
            pytest.param(
                [("t1", "i1", 0, 0), ("t1", "i2", 200, 0)], id="same_macro_apart"
            ),
        ],
    )
    def test_accepts_disjoint_placements(
        self, flow: MagicMock, placements: list[tuple[str, str, int, int]]
    ) -> None:
        """Placements that at most share an edge pass validation."""
        tile_sizes = {tile: (Decimal(100), Decimal(100)) for tile, *_ in placements}

        assert (
            flow._validate_no_macro_overlaps(flow, self._macros(placements), tile_sizes)
            is True
        )

    @pytest.mark.parametrize(
        "placements",
        [
            pytest.param(
                [("t1", "i1", 0, 0), ("t2", "i2", 50, 50)], id="different_macros"
            ),
            pytest.param([("t1", "i1", 0, 0), ("t1", "i2", 50, 50)], id="same_macro"),
        ],
    )
    def test_rejects_overlapping_placements(
        self, flow: MagicMock, placements: list[tuple[str, str, int, int]]
    ) -> None:
        """Two instances whose areas intersect fail, whichever macro they belong to."""
        tile_sizes = {tile: (Decimal(100), Decimal(100)) for tile, *_ in placements}

        with pytest.raises(ValueError, match="overlapping macros detected"):
            flow._validate_no_macro_overlaps(flow, self._macros(placements), tile_sizes)

    def test_instance_without_location(self, flow: MagicMock) -> None:
        """Test handling of instance without location set."""
        instance: Instance = Instance(location=None, orientation=Orientation.N)
        macro: Macro = create_macro({"inst1": instance})

        macros: dict[str, Macro] = {"tile1": macro}
        tile_sizes: dict[str, tuple[Decimal, Decimal]] = {
            "tile1": (Decimal(100), Decimal(100))
        }

        # Should not raise - just logs error
        result: bool = flow._validate_no_macro_overlaps(flow, macros, tile_sizes)
        assert result is True

    def test_tile_not_in_sizes(self, flow: MagicMock) -> None:
        """Test handling when tile is not in tile_sizes."""
        instance: Instance = create_instance(Decimal(0), Decimal(0))
        macro: Macro = create_macro({"inst1": instance})

        macros: dict[str, Macro] = {"unknown_tile": macro}
        tile_sizes: dict[str, Any] = {}  # Empty

        # Should not raise - just logs error
        result: bool = flow._validate_no_macro_overlaps(flow, macros, tile_sizes)
        assert result is True


class TestValidateTileSizes:
    """Tests for _validate_tile_sizes method.

    The X and Y pitches differ, so checking an axis against the other axis's
    pitch changes the outcome.
    """

    @pytest.fixture
    def flow(self, mocker: MockerFixture) -> MagicMock:
        """Create a mock flow with _validate_tile_sizes method bound."""
        mock_flow: MagicMock = mocker.MagicMock(spec=FABulousFabricMacroFlow)
        mock_flow._validate_tile_sizes = FABulousFabricMacroFlow._validate_tile_sizes
        return mock_flow

    @pytest.mark.parametrize(
        ("tile_sizes", "pitch_x", "pitch_y"),
        [
            pytest.param(
                {
                    "tile1": (Decimal(100), Decimal(90)),
                    "tile2": (Decimal(50), Decimal(30)),
                },
                Decimal(50),
                Decimal(30),
                id="aligned",
            ),
            pytest.param(
                {"tile1": (Decimal(75), Decimal(35))},
                Decimal(0),
                Decimal(0),
                id="zero_pitch_skips_check",
            ),
            pytest.param(
                {"tile1": (Decimal("100.00005"), Decimal("89.99995"))},
                Decimal(50),
                Decimal(30),
                id="within_tolerance",
            ),
        ],
    )
    def test_accepts_pitch_aligned_sizes(
        self,
        flow: MagicMock,
        tile_sizes: dict[str, tuple[Decimal, Decimal]],
        pitch_x: Decimal,
        pitch_y: Decimal,
    ) -> None:
        """Widths on the X pitch and heights on the Y pitch pass."""
        assert flow._validate_tile_sizes(flow, tile_sizes, pitch_x, pitch_y) is True

    @pytest.mark.parametrize(
        "tile_sizes",
        [
            pytest.param({"tile1": (Decimal(75), Decimal(90))}, id="width_off_grid"),
            pytest.param({"tile1": (Decimal(100), Decimal(75))}, id="height_off_grid"),
            pytest.param(
                {"tile1": (Decimal("100.001"), Decimal(90))}, id="width_one_dbu_over"
            ),
            pytest.param(
                {"tile1": (Decimal(100), Decimal("89.999"))}, id="height_one_dbu_under"
            ),
        ],
    )
    def test_rejects_misaligned_sizes(
        self,
        flow: MagicMock,
        tile_sizes: dict[str, tuple[Decimal, Decimal]],
    ) -> None:
        """A width off the X pitch or a height off the Y pitch fails."""
        with pytest.raises(ValueError, match="Tile size validation failed"):
            flow._validate_tile_sizes(flow, tile_sizes, Decimal(50), Decimal(30))

    def test_reports_each_misaligned_size_once(
        self, flow: MagicMock, mocker: MockerFixture
    ) -> None:
        """A misaligned tile and a misaligned supertile are each logged once."""
        err = mocker.patch(
            "fabulous.fabric_generator.gds_generator.flows.fabric_macro_flow.err"
        )
        tile_sizes = {
            "tile1": (Decimal(75), Decimal(90)),
            "ST": (Decimal(100), Decimal(75)),
        }

        with pytest.raises(ValueError, match="Tile size validation failed"):
            flow._validate_tile_sizes(flow, tile_sizes, Decimal(50), Decimal(30))

        assert [c.args[0] for c in err.call_args_list] == [
            "Tile sizes validation failed:",
            "  tile1: width 75 not aligned to 50 (remainder: 25)",
            "  ST: height 75 not aligned to 30 (remainder: 15)",
        ]


class TestComputeRowAndColumnSizes:
    """Tests for _compute_row_and_column_sizes method on real fabrics."""

    @pytest.fixture
    def flow(self, mocker: MockerFixture) -> MagicMock:
        """Create a mock flow with _compute_row_and_column_sizes method bound."""
        mock_flow: MagicMock = mocker.MagicMock(spec=FABulousFabricMacroFlow)
        mock_flow._compute_row_and_column_sizes = (
            FABulousFabricMacroFlow._compute_row_and_column_sizes
        )
        return mock_flow

    def test_compute_sizes_full_grid(self, flow: MagicMock) -> None:
        """A 2-row x 3-column grid gives one height per row, one width per column."""
        fabric: Fabric = make_fabric_from_grid(
            [
                [_tile("A"), _tile("B"), _tile("C")],
                [_tile("D"), _tile("E"), _tile("F")],
            ]
        )
        tile_sizes: dict[str, tuple[Decimal, Decimal]] = {
            "A": (Decimal(100), Decimal(50)),
            "B": (Decimal(200), Decimal(50)),
            "C": (Decimal(150), Decimal(50)),
            "D": (Decimal(100), Decimal(75)),
            "E": (Decimal(200), Decimal(75)),
            "F": (Decimal(150), Decimal(75)),
        }

        assert flow._compute_row_and_column_sizes(flow, fabric, tile_sizes) == (
            [Decimal(50), Decimal(75)],
            [Decimal(100), Decimal(200), Decimal(150)],
        )

    def test_compute_sizes_with_none_tiles(self, flow: MagicMock) -> None:
        """Null grid cells are skipped; sizes come from the tiles that are present."""
        # Only the diagonal is populated, so each row and column is sized by
        # exactly one tile.
        fabric: Fabric = make_fabric_from_grid(
            [[_tile("tile1"), None], [None, _tile("tile2")]]
        )
        tile_sizes: dict[str, tuple[Decimal, Decimal]] = {
            "tile1": (Decimal(100), Decimal(50)),
            "tile2": (Decimal(200), Decimal(75)),
        }

        assert flow._compute_row_and_column_sizes(flow, fabric, tile_sizes) == (
            [Decimal(50), Decimal(75)],
            [Decimal(100), Decimal(200)],
        )

    @pytest.mark.parametrize(
        ("grid_names", "tile_sizes", "message"),
        [
            pytest.param(
                [["tile1"], ["tile2"]],
                {
                    "tile1": (Decimal(100), Decimal(50)),
                    "tile2": (Decimal(150), Decimal(50)),
                },
                "Non-uniform tile widths in column 0 for tile: tile2",
                id="width_in_column",
            ),
            pytest.param(
                [["tile1", "tile2"]],
                {
                    "tile1": (Decimal(100), Decimal(50)),
                    "tile2": (Decimal(100), Decimal(75)),
                },
                "Non-uniform tile heights in row 0 for tile: tile2",
                id="height_in_row",
            ),
        ],
    )
    def test_compute_sizes_non_uniform_raises_error(
        self,
        flow: MagicMock,
        grid_names: list[list[str]],
        tile_sizes: dict[str, tuple[Decimal, Decimal]],
        message: str,
    ) -> None:
        """Tiles sharing a column must agree on width, sharing a row on height."""
        fabric: Fabric = make_fabric_from_grid(
            [[_tile(name) for name in row] for row in grid_names]
        )

        with pytest.raises(ValueError, match=message):
            flow._compute_row_and_column_sizes(flow, fabric, tile_sizes)


class TestSpacingVariableTypes:
    """Type-system checks for the Union-typed spacing variables.

    The spacing variables accept either a scalar (applied to both axes) or a
    tuple (per-axis). Real example projects use *both* shapes:
    - ``tt-fabulous-ihp-26a/fabrics/tiny_fabric_9x5/config.yaml`` uses
      ``FABULOUS_TILE_SPACING: 0`` (scalar).
    - ``tests/assets/librelane_plugin/.../config.yaml`` uses ``[0, 0]`` (tuple).

    YAML-loaded values reach LibreLane as bare ``int``/``str``/``list``, so
    ``Variable.compile`` is invoked with ``permissive_typing=True``. These
    tests assert both shapes survive that pipeline and produce the
    Decimal-typed shapes that ``run()``'s normalization expects.
    """

    @staticmethod
    def _compile_var(name: str, value: object) -> object:
        """Compile a config var the same way LibreLane does for YAML inputs."""
        from librelane.common import GenericDict

        var = next(v for v in configs if v.name == name)
        _, compiled = var.compile(
            GenericDict({name: value}),
            warning_list_ref=[],
            permissive_typing=True,
        )
        return compiled

    def test_tile_spacing_accepts_scalar(self) -> None:
        v = self._compile_var("FABULOUS_TILE_SPACING", 5)
        assert v == Decimal(5)
        assert isinstance(v, Decimal)

    def test_tile_spacing_accepts_2_tuple(self) -> None:
        v = self._compile_var("FABULOUS_TILE_SPACING", [3, 7])
        assert v == (Decimal(3), Decimal(7))
        assert isinstance(v, tuple)
        assert all(isinstance(x, Decimal) for x in v)

    def test_tile_spacing_default_compiles(self) -> None:
        """Default ``(0, 0)`` must satisfy its own type."""
        from librelane.common import GenericDict

        var = next(v for v in configs if v.name == "FABULOUS_TILE_SPACING")
        # Empty input → falls back to default; compile must not raise.
        _, v = var.compile(GenericDict({}), warning_list_ref=[], permissive_typing=True)
        assert v == (Decimal(0), Decimal(0))

    def test_halo_spacing_accepts_scalar(self) -> None:
        v = self._compile_var("FABULOUS_HALO_SPACING", 4)
        assert v == Decimal(4)
        assert isinstance(v, Decimal)

    def test_halo_spacing_accepts_4_tuple(self) -> None:
        v = self._compile_var("FABULOUS_HALO_SPACING", [1, 2, 3, 4])
        assert v == (Decimal(1), Decimal(2), Decimal(3), Decimal(4))
        assert isinstance(v, tuple)
        assert all(isinstance(x, Decimal) for x in v)

    def test_halo_spacing_default_compiles(self) -> None:
        from librelane.common import GenericDict

        var = next(v for v in configs if v.name == "FABULOUS_HALO_SPACING")
        _, v = var.compile(GenericDict({}), warning_list_ref=[], permissive_typing=True)
        assert v == (Decimal(0), Decimal(0), Decimal(0), Decimal(0))

    def test_tile_spacing_rejects_wrong_arity_tuple(self) -> None:
        """A 3-tuple must be rejected — only scalar or 2-tuple are valid."""
        with pytest.raises(ValueError, match="FABULOUS_TILE_SPACING"):
            self._compile_var("FABULOUS_TILE_SPACING", [1, 2, 3])

    def test_halo_spacing_rejects_wrong_arity_tuple(self) -> None:
        """A 2-tuple must be rejected for halo — only scalar or 4-tuple."""
        with pytest.raises(ValueError, match="FABULOUS_HALO_SPACING"):
            self._compile_var("FABULOUS_HALO_SPACING", [1, 2])


class TestFlowSubstitutions:
    """The class-level `Substitutions` reach `Steps` on both HDL variants."""

    # Placement, timing repair and STA steps a macro-only fabric must not run.
    REMOVED_STEP_IDS: frozenset[str] = frozenset(
        {
            "OpenROAD.CutRows",
            "OpenROAD.TapEndcapInsertion",
            "OpenROAD.STAPrePNR",
            "OpenROAD.STAMidPNR",
            "OpenROAD.STAPostPNR",
            "OpenROAD.GeneratePDN",
            "Odb.CustomIOPlacement",
            "Odb.ApplyDEFTemplate",
            "OpenROAD.GlobalPlacement",
            "Odb.ManualGlobalPlacement",
            "OpenROAD.DetailedPlacement",
            "OpenROAD.RepairDesignPostGPL",
            "OpenROAD.RepairDesignPostGRT",
            "OpenROAD.RepairAntennas",
            "OpenROAD.ResizerTimingPostCTS",
            "OpenROAD.ResizerTimingPostGRT",
            "OpenROAD.RCX",
            "OpenROAD.IRDropReport",
        }
    )

    @pytest.mark.parametrize(
        "flow_cls", [FABulousFabricMacroFlow, FABulousFabricVHDLMacroFlow]
    )
    def test_substituted_steps(self, flow_cls: type[FABulousFabricMacroFlow]) -> None:
        """Removed steps are gone and the IO placer / PDN are the FABulous ones."""
        assert {step.id for step in physical_steps} >= self.REMOVED_STEP_IDS

        step_ids: set[str] = {step.id for step in flow_cls.Steps}

        assert step_ids.isdisjoint(self.REMOVED_STEP_IDS)
        assert {FABulousFabricIOPlacement, FABulousPDN} <= set(flow_cls.Steps)
