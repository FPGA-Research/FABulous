"""Tests for FABulousTileVerilogMacroFlow - Tile macro generation flow.

Tests focus on:
- Flow initialization with various parameters
- Configuration merging and validation
- OptMode handling
- DIE_AREA validation
- Logical dimension calculation for Tile vs SuperTile
- Routing obstructions generation
- Error handling for invalid configurations

Note: These tests use shared fixtures from conftest.py that mock the PDK
and Config.load to avoid requiring actual PDK files.
"""

from decimal import Decimal
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock

import pytest
import yaml
from librelane.flows.flow import FlowException
from pytest_mock import MockerFixture

from fabulous.fabric_generator.gds_generator.flows.tile_macro_flow import (
    FABulousTileVerilogMacroFlow,
)
from fabulous.fabric_generator.gds_generator.steps.tile_area_opt import OptMode


@pytest.mark.usefixtures("mock_config_load")
class TestFABulousTileVerilogMacroFlowInit:
    """Tests for FABulousTileVerilogMacroFlow initialization and configuration."""

    def _create_flow(
        self,
        *,
        tile_type: MagicMock,
        io_pin_config: Path,
        mock_pdk_root: dict[str, Any],
        opt_mode: OptMode | None = OptMode.FIND_MIN_WIDTH,
        **kwargs: dict,
    ) -> FABulousTileVerilogMacroFlow:
        """Create a flow with shared defaults used across tests."""
        flow_kwargs: dict[str, Any] = {
            "tile_type": tile_type,
            "io_pin_config": io_pin_config,
            "opt_mode": opt_mode,
            "pdk": mock_pdk_root["pdk"],
            "pdk_root": mock_pdk_root["pdk_root"],
            "models_pack_path": Path("/fake/models/pack"),
        }
        flow_kwargs.update(kwargs)
        return FABulousTileVerilogMacroFlow(**flow_kwargs)

    def test_init_with_basic_tile(
        self,
        mock_tile: MagicMock,
        io_pin_config: Path,
        mock_pdk_root: dict[str, Any],
    ) -> None:
        """Test initialization with a basic Tile."""
        flow: FABulousTileVerilogMacroFlow = self._create_flow(
            tile_type=mock_tile,
            io_pin_config=io_pin_config,
            mock_pdk_root=mock_pdk_root,
        )

        assert flow.config["DESIGN_NAME"] == "TestTile"
        assert flow.config["FABULOUS_OPT_MODE"] == OptMode.FIND_MIN_WIDTH
        assert flow.config["FABULOUS_TILE_LOGICAL_WIDTH"] == 1
        assert flow.config["FABULOUS_TILE_LOGICAL_HEIGHT"] == 1
        assert flow.config["FABULOUS_IO_PIN_ORDER_CFG"] == str(io_pin_config)

    def test_init_with_supertile(
        self,
        mock_supertile: MagicMock,
        io_pin_config: Path,
        mock_pdk_root: dict[str, Any],
    ) -> None:
        """Test initialization with a SuperTile sets correct logical dimensions."""
        flow: FABulousTileVerilogMacroFlow = self._create_flow(
            tile_type=mock_supertile,
            io_pin_config=io_pin_config,
            opt_mode=OptMode.FIND_MIN_HEIGHT,
            mock_pdk_root=mock_pdk_root,
        )

        assert flow.config["DESIGN_NAME"] == "TestSuperTile"
        assert flow.config["FABULOUS_TILE_LOGICAL_WIDTH"] == 4
        assert flow.config["FABULOUS_TILE_LOGICAL_HEIGHT"] == 3

    def test_config_merging_precedence(
        self,
        mock_tile: MagicMock,
        io_pin_config: Path,
        base_config_file: Path,
        override_config_file: Path,
        mock_pdk_root: dict[str, Any],
    ) -> None:
        """Test config merging follows correct precedence: custom > override > base."""
        flow: FABulousTileVerilogMacroFlow = self._create_flow(
            tile_type=mock_tile,
            io_pin_config=io_pin_config,
            mock_pdk_root=mock_pdk_root,
            base_config_path=base_config_file,
            override_config_path=override_config_file,
            OVERRIDE_ME="custom",
            CUSTOM_VAR="custom_value",
        )

        assert flow.config["BASE_VAR"] == "base_value"
        assert flow.config["OVERRIDE_VAR"] == "override_value"
        assert flow.config["OVERRIDE_ME"] == "custom"
        assert flow.config["CUSTOM_VAR"] == "custom_value"

    def test_opt_mode_string_conversion(
        self,
        mock_tile: MagicMock,
        io_pin_config: Path,
        mock_pdk_root: dict[str, Any],
    ) -> None:
        """Test that string FABULOUS_OPT_MODE is converted to OptMode enum."""
        flow: FABulousTileVerilogMacroFlow = self._create_flow(
            tile_type=mock_tile,
            io_pin_config=io_pin_config,
            mock_pdk_root=mock_pdk_root,
            FABULOUS_OPT_MODE="find_min_height",
        )

        assert flow.config["FABULOUS_OPT_MODE"] == OptMode.FIND_MIN_HEIGHT
        assert isinstance(flow.config["FABULOUS_OPT_MODE"], OptMode)

    def test_min_die_area_uses_io_pin_thickness_multipliers(
        self,
        mock_tile: MagicMock,
        io_pin_config: Path,
        mock_pdk_root: dict[str, Any],
    ) -> None:
        """Test IO pin thickness multipliers are forwarded to min die area calc."""
        self._create_flow(
            tile_type=mock_tile,
            io_pin_config=io_pin_config,
            mock_pdk_root=mock_pdk_root,
            IO_PIN_V_THICKNESS_MULT=Decimal("2.0"),
            IO_PIN_H_THICKNESS_MULT=Decimal("3.0"),
        )

        mock_tile.get_min_die_area.assert_called_once_with(
            x_pitch=Decimal("0.28"),
            y_pitch=Decimal("0.56"),
            x_pin_thickness_mult=Decimal("2.0"),
            y_pin_thickness_mult=Decimal("3.0"),
        )

    def test_die_area_set_with_ignore_default(
        self,
        mock_tile: MagicMock,
        io_pin_config: Path,
        mock_pdk_root: dict[str, Any],
    ) -> None:
        """Test DIE_AREA is set when FABULOUS_IGNORE_DEFAULT_DIE_AREA is True."""
        flow: FABulousTileVerilogMacroFlow = self._create_flow(
            tile_type=mock_tile,
            io_pin_config=io_pin_config,
            mock_pdk_root=mock_pdk_root,
            FABULOUS_IGNORE_DEFAULT_DIE_AREA=True,
        )

        die_area: tuple[int, int, Decimal, Decimal] = flow.config["DIE_AREA"]
        # DIE_AREA is rounded to pitch multiples (0.28 for X, 0.56 for Y)
        # 100.0 / 0.28 = 357.14... -> 358 * 0.28 = 100.24
        # 100.0 / 0.56 = 178.57... -> 179 * 0.56 = 100.24
        assert die_area == (0, 0, Decimal("100.24"), Decimal("100.24"))

    @pytest.mark.parametrize(
        ("opt_mode", "min_area", "user_area", "expected_area"),
        [
            # 50.0 / 0.28 -> 179 * 0.28 = 50.12; 150.0 / 0.56 -> 268 * 0.56 = 150.08
            pytest.param(
                OptMode.FIND_MIN_WIDTH,
                (Decimal("200.0"), Decimal("100.0")),
                (Decimal("50.0"), Decimal("150.0")),
                (Decimal("50.12"), Decimal("150.08")),
                id="find_min_width_fixes_height",
            ),
            # 150.0 / 0.28 -> 536 * 0.28 = 150.08; 50.0 / 0.56 -> 90 * 0.56 = 50.40
            pytest.param(
                OptMode.FIND_MIN_HEIGHT,
                (Decimal("100.0"), Decimal("200.0")),
                (Decimal("150.0"), Decimal("50.0")),
                (Decimal("150.08"), Decimal("50.40")),
                id="find_min_height_fixes_width",
            ),
        ],
    )
    def test_directional_honours_user_fixed_axis(
        self,
        mock_tile: MagicMock,
        io_pin_config: Path,
        mock_pdk_root: dict[str, Any],
        opt_mode: OptMode,
        min_area: tuple[Decimal, Decimal],
        user_area: tuple[Decimal, Decimal],
        expected_area: tuple[Decimal, Decimal],
    ) -> None:
        """The fixed axis keeps the user value; the minimised axis may be below
        its physical minimum."""
        mock_tile.get_min_die_area.return_value = min_area

        flow: FABulousTileVerilogMacroFlow = self._create_flow(
            tile_type=mock_tile,
            io_pin_config=io_pin_config,
            mock_pdk_root=mock_pdk_root,
            opt_mode=opt_mode,
            DIE_AREA=(0, 0, *user_area),
        )

        assert flow.config["FABULOUS_IGNORE_DEFAULT_DIE_AREA"] is False
        assert flow.config["DIE_AREA"] == (0, 0, *expected_area)

    @pytest.mark.parametrize(
        ("opt_mode", "min_area", "user_area", "message"),
        [
            pytest.param(
                OptMode.FIND_MIN_WIDTH,
                (Decimal("200.0"), Decimal("100.0")),
                (Decimal("500.0"), Decimal("50.0")),
                "Fixed height (50.0) is smaller than the minimum required height "
                "(100.0) to fit the IO pins of tile TestTile. Increase the "
                "DIE_AREA height or pick a different optimisation mode.",
                id="find_min_width_height_below_min",
            ),
            pytest.param(
                OptMode.FIND_MIN_HEIGHT,
                (Decimal("100.0"), Decimal("200.0")),
                (Decimal("50.0"), Decimal("500.0")),
                "Fixed width (50.0) is smaller than the minimum required width "
                "(100.0) to fit the IO pins of tile TestTile. Increase the "
                "DIE_AREA width or pick a different optimisation mode.",
                id="find_min_height_width_below_min",
            ),
            pytest.param(
                OptMode.BALANCE,
                (Decimal("100.0"), Decimal("100.0")),
                (Decimal("300.0"), Decimal("50.0")),
                "DIE_AREA (300.0, 50.0) is smaller than the minimum required area "
                "(100.0, 100.0) for the tile TestTile. Please update the DIE_AREA ",
                id="balance_height_below_min",
            ),
        ],
    )
    def test_rejects_user_die_area_below_physical_min(
        self,
        mock_tile: MagicMock,
        io_pin_config: Path,
        mock_pdk_root: dict[str, Any],
        opt_mode: OptMode,
        min_area: tuple[Decimal, Decimal],
        user_area: tuple[Decimal, Decimal],
        message: str,
    ) -> None:
        """A constrained axis below the IO-pin minimum is rejected, naming it.

        Directional modes only constrain the fixed axis, so the minimised axis
        is comfortably above its minimum here; balance constrains both.
        """
        mock_tile.get_min_die_area.return_value = min_area

        with pytest.raises(FlowException) as exc_info:
            self._create_flow(
                tile_type=mock_tile,
                io_pin_config=io_pin_config,
                mock_pdk_root=mock_pdk_root,
                opt_mode=opt_mode,
                DIE_AREA=(0, 0, *user_area),
            )

        assert str(exc_info.value) == message

    @pytest.mark.parametrize("opt_mode", [OptMode.BALANCE, OptMode.LARGE])
    def test_non_directional_honours_user_die_area(
        self,
        mock_tile: MagicMock,
        io_pin_config: Path,
        mock_pdk_root: dict[str, Any],
        opt_mode: OptMode,
    ) -> None:
        """balance/large grow from the user DIE_AREA instead of the pin minimum.

        A tile holding a hard macro cannot start from the pin-derived minimum, so
        the user DIE_AREA is the starting area the optimisation grows from.
        """
        mock_tile.get_min_die_area.return_value = (Decimal("100.0"), Decimal("100.0"))

        flow: FABulousTileVerilogMacroFlow = self._create_flow(
            tile_type=mock_tile,
            io_pin_config=io_pin_config,
            mock_pdk_root=mock_pdk_root,
            opt_mode=opt_mode,
            DIE_AREA=(0, 0, Decimal("300.0"), Decimal("300.0")),
        )

        assert flow.config["FABULOUS_IGNORE_DEFAULT_DIE_AREA"] is False
        # 300.0 / 0.28 = 1071.42... -> 1072 * 0.28 = 300.16
        # 300.0 / 0.56 = 535.71... -> 536 * 0.56 = 300.16
        assert flow.config["DIE_AREA"] == (0, 0, Decimal("300.16"), Decimal("300.16"))

    @pytest.mark.parametrize("opt_mode", [OptMode.BALANCE, OptMode.LARGE])
    def test_non_directional_discards_user_die_area_when_ignoring(
        self,
        mock_tile: MagicMock,
        io_pin_config: Path,
        mock_pdk_root: dict[str, Any],
        opt_mode: OptMode,
    ) -> None:
        """FABULOUS_IGNORE_DEFAULT_DIE_AREA restores full-auto sizing."""
        mock_tile.get_min_die_area.return_value = (Decimal("100.0"), Decimal("100.0"))

        flow: FABulousTileVerilogMacroFlow = self._create_flow(
            tile_type=mock_tile,
            io_pin_config=io_pin_config,
            mock_pdk_root=mock_pdk_root,
            opt_mode=opt_mode,
            DIE_AREA=(0, 0, Decimal("300.0"), Decimal("300.0")),
            FABULOUS_IGNORE_DEFAULT_DIE_AREA=True,
        )

        # 100.0 / 0.28 = 357.14... -> 358 * 0.28 = 100.24
        # 100.0 / 0.56 = 178.57... -> 179 * 0.56 = 100.24
        assert flow.config["DIE_AREA"] == (0, 0, Decimal("100.24"), Decimal("100.24"))

    def test_no_opt_mode_requires_die_area(
        self,
        mock_tile: MagicMock,
        io_pin_config: Path,
        mock_pdk_root: dict[str, Any],
    ) -> None:
        """Test that NO_OPT mode requires DIE_AREA to be set."""
        with pytest.raises(FlowException, match="Invalid DIE_AREA configuration"):
            self._create_flow(
                tile_type=mock_tile,
                io_pin_config=io_pin_config,
                opt_mode=OptMode.NO_OPT,
                mock_pdk_root=mock_pdk_root,
            )

    def test_no_opt_mode_with_die_area(
        self,
        mock_tile: MagicMock,
        io_pin_config: Path,
        mock_pdk_root: dict[str, Any],
    ) -> None:
        """Test that NO_OPT mode works when DIE_AREA is provided."""
        flow: FABulousTileVerilogMacroFlow = self._create_flow(
            tile_type=mock_tile,
            io_pin_config=io_pin_config,
            opt_mode=OptMode.NO_OPT,
            mock_pdk_root=mock_pdk_root,
            DIE_AREA=(0, 0, Decimal("200.0"), Decimal("200.0")),
        )

        # DIE_AREA is rounded to pitch multiples (0.28 for X, 0.56 for Y)
        # 200.0 / 0.28 = 714.28... -> 715 * 0.28 = 200.20
        # 200.0 / 0.56 = 357.14... -> 358 * 0.56 = 200.48
        assert flow.config["DIE_AREA"] == (0, 0, Decimal("200.20"), Decimal("200.48"))

    def test_routing_obstructions_generated(
        self,
        mock_tile: MagicMock,
        io_pin_config: Path,
        mock_pdk_root: dict[str, Any],
    ) -> None:
        """Generated obstructions guard every die edge on every routing layer."""
        flow: FABulousTileVerilogMacroFlow = self._create_flow(
            tile_type=mock_tile,
            io_pin_config=io_pin_config,
            mock_pdk_root=mock_pdk_root,
        )

        obstructions: list[tuple[str, Decimal, Decimal, Decimal, Decimal]] = (
            flow.config["ROUTING_OBSTRUCTIONS"]
        )

        # Four half-pitch guard bands (one per die edge) for each of the four
        # layers in the mock tracks file, around the 100.24 x 100.24 die.
        assert len(obstructions) == 16
        # M1 has a 0.28 pitch on both axes, so its bands are 0.14 deep.
        assert [obs for obs in obstructions if obs[0] == "M1"] == [
            ("M1", Decimal(0), Decimal("-0.14"), Decimal("100.24"), Decimal(0)),
            (
                "M1",
                Decimal(0),
                Decimal("100.24"),
                Decimal("100.24"),
                Decimal("100.38"),
            ),
            ("M1", Decimal("-0.14"), Decimal(0), Decimal(0), Decimal("100.24")),
            (
                "M1",
                Decimal("100.24"),
                Decimal(0),
                Decimal("100.38"),
                Decimal("100.24"),
            ),
        ]

    def test_routing_obstructions_not_generated_when_false(
        self,
        mock_tile: MagicMock,
        io_pin_config: Path,
        mock_pdk_root: dict[str, Any],
    ) -> None:
        """Test that routing obstructions are not generated when explicitly False."""
        flow: FABulousTileVerilogMacroFlow = self._create_flow(
            tile_type=mock_tile,
            io_pin_config=io_pin_config,
            mock_pdk_root=mock_pdk_root,
            ROUTING_OBSTRUCTIONS=False,
        )

        assert flow.config["ROUTING_OBSTRUCTIONS"] is False

    def test_routing_obstructions_custom_value(
        self,
        mock_tile: MagicMock,
        io_pin_config: Path,
        mock_pdk_root: dict[str, Any],
    ) -> None:
        """Test that custom routing obstructions value is preserved."""
        custom_obstructions: list[tuple[str, int, int, int, int]] = [
            ("M1", 0, 0, 10, 10)
        ]
        flow: FABulousTileVerilogMacroFlow = self._create_flow(
            tile_type=mock_tile,
            io_pin_config=io_pin_config,
            mock_pdk_root=mock_pdk_root,
            ROUTING_OBSTRUCTIONS=custom_obstructions,
        )

        assert flow.config["ROUTING_OBSTRUCTIONS"] == custom_obstructions

    def test_design_dir_default(
        self,
        mock_tile: MagicMock,
        io_pin_config: Path,
        mock_pdk_root: dict[str, Any],
    ) -> None:
        """The flow runs in `<tile>/macro/<opt_mode>` when no design_dir is given."""
        flow: FABulousTileVerilogMacroFlow = self._create_flow(
            tile_type=mock_tile,
            io_pin_config=io_pin_config,
            mock_pdk_root=mock_pdk_root,
        )

        expected_dir: Path = mock_tile.tileDir.parent / "macro" / "find_min_width"
        assert flow.design_dir == str(expected_dir.resolve())

    def test_design_dir_custom(
        self,
        mock_tile: MagicMock,
        io_pin_config: Path,
        mock_pdk_root: dict[str, Any],
        tmp_path: Path,
    ) -> None:
        """Test that custom design_dir is used when provided."""
        custom_dir: Path = tmp_path / "custom_design_dir"
        custom_dir.mkdir()

        flow: FABulousTileVerilogMacroFlow = self._create_flow(
            tile_type=mock_tile,
            io_pin_config=io_pin_config,
            mock_pdk_root=mock_pdk_root,
            design_dir=custom_dir,
        )

        assert flow.design_dir == str(custom_dir)

    def test_verilog_files_collected(
        self,
        mock_tile: MagicMock,
        io_pin_config: Path,
        mock_pdk_root: dict[str, Any],
    ) -> None:
        """VERILOG_FILES holds the tile sources, then the models pack."""
        flow: FABulousTileVerilogMacroFlow = self._create_flow(
            tile_type=mock_tile,
            io_pin_config=io_pin_config,
            mock_pdk_root=mock_pdk_root,
            models_pack_path=Path("/fake/models/pack.v"),
        )

        verilog_files: list[str] = flow.config["VERILOG_FILES"]
        assert verilog_files == [
            str(mock_tile.tileDir.parent / "test.v"),
            "/fake/models/pack.v",
        ]

    def test_verilog_files_include_out_of_tree_bel_source(
        self,
        mock_tile: MagicMock,
        io_pin_config: Path,
        mock_pdk_root: dict[str, Any],
        tmp_path: Path,
        mocker: MockerFixture,
    ) -> None:
        """BEL sources outside the tile directory are appended once.

        A BEL referenced by a relative path in the tile CSV (e.g. a shared
        primitive under `primitives/`) lives outside the tile glob, so it
        must be picked up from the tile's BEL list instead. A BEL whose source
        the glob already found is not listed twice.
        """
        in_tree_src: Path = mock_tile.tileDir.parent / "test.v"
        bel_src: Path = tmp_path / "primitives" / "SRAM" / "fabulous" / "SRAM.v"
        bel_src.parent.mkdir(parents=True)
        bel_src.write_text("module SRAM(); endmodule")
        mock_tile.bels = [
            mocker.MagicMock(src=in_tree_src),
            mocker.MagicMock(src=bel_src),
        ]

        flow: FABulousTileVerilogMacroFlow = self._create_flow(
            tile_type=mock_tile,
            io_pin_config=io_pin_config,
            mock_pdk_root=mock_pdk_root,
            models_pack_path=Path("/fake/models/pack.v"),
        )

        assert flow.config["VERILOG_FILES"] == [
            str(in_tree_src),
            "/fake/models/pack.v",
            str(bel_src),
        ]

    @pytest.mark.parametrize(
        "second_src_parts",
        [
            pytest.param(("SRAM.v",), id="same_path"),
            pytest.param(("..", "fabulous", "SRAM.v"), id="through_parent_dir"),
        ],
    )
    def test_verilog_files_include_subtile_bel_source(
        self,
        mock_supertile: MagicMock,
        io_pin_config: Path,
        mock_pdk_root: dict[str, Any],
        tmp_path: Path,
        mocker: MockerFixture,
        second_src_parts: tuple[str, ...],
    ) -> None:
        """SuperTile sub-tile BEL sources are added to VERILOG_FILES once.

        SuperTile BELs live on the constituent sub-tiles rather than the
        wrapper, so collection must descend into `SuperTile.tiles`; two
        sub-tiles sharing a primitive contribute it once, also when they
        reach it through different relative paths.
        """
        bel_dir: Path = tmp_path / "primitives" / "SRAM" / "fabulous"
        bel_src: Path = bel_dir / "SRAM.v"
        bel_dir.mkdir(parents=True)
        bel_src.write_text("module SRAM(); endmodule")
        mock_supertile.tiles = [
            mocker.MagicMock(bels=[mocker.MagicMock(src=bel_src)]),
            mocker.MagicMock(
                bels=[mocker.MagicMock(src=bel_dir.joinpath(*second_src_parts))]
            ),
        ]

        flow: FABulousTileVerilogMacroFlow = self._create_flow(
            tile_type=mock_supertile,
            io_pin_config=io_pin_config,
            mock_pdk_root=mock_pdk_root,
            models_pack_path=Path("/fake/models/pack.v"),
        )

        assert flow.config["VERILOG_FILES"] == [
            str(mock_supertile.tileDir.parent / "test.v"),
            "/fake/models/pack.v",
            str(bel_src),
        ]

    def test_nonexistent_config_files_ignored(
        self,
        mock_tile: MagicMock,
        io_pin_config: Path,
        mock_pdk_root: dict[str, Any],
        tmp_path: Path,
    ) -> None:
        """Test that nonexistent config files don't cause errors."""
        nonexistent: Path = tmp_path / "nonexistent.yaml"

        flow: FABulousTileVerilogMacroFlow = self._create_flow(
            tile_type=mock_tile,
            io_pin_config=io_pin_config,
            mock_pdk_root=mock_pdk_root,
            base_config_path=nonexistent,
            override_config_path=nonexistent,
        )

        assert flow.config["DESIGN_NAME"] == "TestTile"

    def test_substituting_steps_from_base_config_applied(
        self,
        mock_tile: MagicMock,
        io_pin_config: Path,
        mock_pdk_root: dict[str, Any],
        base_config_file: Path,
        override_config_file: Path,
    ) -> None:
        """`meta.substituting_steps` in `base_config_path` must reach `Steps`.

        Regression test: `Config.load()` overwrites `Config.meta` per config
        source instead of merging, so a later source (`override_config_path`
        here, which carries no `meta:` key) used to silently drop the
        substitutions defined in an earlier source.
        """
        meta_yaml: str = base_config_file.read_text()
        base_config_file.write_text(
            meta_yaml
            + "\n"
            + yaml.dump({"meta": {"substituting_steps": {"KLayout.XOR": None}}})
        )

        flow: FABulousTileVerilogMacroFlow = self._create_flow(
            tile_type=mock_tile,
            io_pin_config=io_pin_config,
            mock_pdk_root=mock_pdk_root,
            base_config_path=base_config_file,
            override_config_path=override_config_file,
        )

        assert not any(step.id == "KLayout.XOR" for step in flow.Steps)

    def test_none_cast_to_no_opt(
        self,
        mock_tile: MagicMock,
        io_pin_config: Path,
        mock_pdk_root: dict[str, Any],
    ) -> None:
        """Test none handling for opt_mode results in NO_OPT."""

        flow: FABulousTileVerilogMacroFlow = self._create_flow(
            tile_type=mock_tile,
            io_pin_config=io_pin_config,
            mock_pdk_root=mock_pdk_root,
            opt_mode=None,
            DIE_AREA=(0, 0, Decimal("200.0"), Decimal("200.0")),
        )

        assert flow.config["FABULOUS_OPT_MODE"] == OptMode.NO_OPT
