"""Tests for the `FABulousTile` LibreLane-plugin adapter.

These tests verify the *adapting* layer: how `FABulousTile` translates
plugin-level config variables and tile-directory inputs into what the
underlying :class:`FABulousTileVerilogMacroFlow` pipeline expects. They do not
exercise the real LibreLane pipeline (that is covered elsewhere).
"""

# ruff: noqa: SLF001

from decimal import Decimal
from pathlib import Path
from unittest.mock import MagicMock

import pytest
from librelane.flows.flow import Flow, FlowException
from pytest_mock import MockerFixture

from fabulous.fabric_definition.define import ConfigBitMode, MultiplexerStyle, Side
from fabulous.fabric_generator.gds_generator.flows import plugin_tile_flow
from fabulous.fabric_generator.gds_generator.flows.plugin_tile_flow import (
    FABulousTile,
    _emit_tile_verilog,
)
from fabulous.fabric_generator.gds_generator.flows.tile_macro_flow import (
    FABulousTileVerilogMacroFlow,
)
from fabulous.fabric_generator.gds_generator.steps.tile_area_opt import OptMode


class TestFABulousTileSchema:
    """Schema-level assertions for the plugin wrapper."""

    def test_registered_in_flow_factory(self) -> None:
        """LibreLane must be able to resolve the flow by name."""
        assert Flow.factory.get("FABulousTile") is FABulousTile

    def test_config_vars_extend_underlying_flow(self) -> None:
        """The underlying flow's vars come first, so LibreLane validates the full
        schema against a single class, followed by exactly the plugin vars."""
        names: list[str] = [v.name for v in FABulousTile.config_vars]
        underlying: list[str] = [
            v.name for v in FABulousTileVerilogMacroFlow.config_vars
        ]

        assert names[: len(underlying)] == underlying
        assert names[len(underlying) :] == [
            "FABULOUS_TILE_DIR",
            "FABULOUS_EXTERNAL_SIDE",
            "FABULOUS_SUPERTILE",
            "FABULOUS_CONFIG_BIT_MODE",
            "FABULOUS_MULTIPLEXER_STYLE",
        ]

    def test_inherits_steps_from_underlying_flow(self) -> None:
        """`Steps` matches the underlying flow (SequentialFlow may copy)."""
        assert FABulousTile.Steps == FABulousTileVerilogMacroFlow.Steps

    def test_inherits_gating_config_vars(self) -> None:
        """Gating vars come from the underlying flow unchanged."""
        assert (
            FABulousTile.gating_config_vars
            == FABulousTileVerilogMacroFlow.gating_config_vars
        )

    @pytest.mark.parametrize(
        ("name", "default"),
        [
            ("FABULOUS_SUPERTILE", False),
            ("FABULOUS_CONFIG_BIT_MODE", ConfigBitMode.FRAME_BASED),
            ("FABULOUS_MULTIPLEXER_STYLE", MultiplexerStyle.CUSTOM),
        ],
    )
    def test_optional_plugin_var_defaults(self, name: str, default: object) -> None:
        """Plugin vars users may omit default to a standard tile build."""
        var = next(v for v in FABulousTile.config_vars if v.name == name)
        assert var.default == default

    def test_fabulous_io_pin_order_cfg_is_optional_on_step(self) -> None:
        """`FABULOUS_IO_PIN_ORDER_CFG` must be optional on the step.

        The FABulous IO placer is fully automated: the plugin generates the
        pin-order YAML inside `run()` and users of the plugin should never
        have to set this variable by hand. If the step declares the variable
        as required without a default, LibreLane's `Config.load` rejects
        any mole99-style `config.yaml` before `run()` can supply a real
        value.
        """
        from fabulous.fabric_generator.gds_generator.steps.tile_IO_placement import (
            FABulousTileIOPlacement,
        )

        var = next(
            v
            for v in FABulousTileIOPlacement.config_vars
            if v.name == "FABULOUS_IO_PIN_ORDER_CFG"
        )
        type_str = str(var.type)
        allows_none = "None" in type_str or "Optional" in type_str
        has_default = var.default is not None or allows_none
        assert allows_none or has_default, (
            f"FABULOUS_IO_PIN_ORDER_CFG must be optional (type={var.type!r}, "
            f"default={var.default!r}) — the automated placer generates it."
        )

    def test_fabulous_tile_dir_accepts_dir_resolver_list(self, tmp_path: Path) -> None:
        """`FABULOUS_TILE_DIR` must validate when set to `dir::...`.

        LibreLane rewrites `dir::.` to `refg::$DESIGN_DIR/.` and the refg
        resolver always produces a `list[str]` (see
        `librelane/config/preprocessor.py`). If the Variable is typed as a
        scalar `Path` the type validator crashes with
        `TypeError: argument should be ... not 'list'` before `run()` ever
        executes, making `dir::.` unusable for this variable.
        """
        from librelane.common import GenericDict

        var = next(v for v in FABulousTile.config_vars if v.name == "FABULOUS_TILE_DIR")
        resolved_list: list[str] = [str(tmp_path)]
        mutable = GenericDict({"FABULOUS_TILE_DIR": resolved_list})
        _, value = var.compile(mutable, warning_list_ref=[])

        # Concrete tile_dir must be recoverable from whatever type we accept.
        tile_dir_path = Path(value[0]) if isinstance(value, list) else Path(value)
        assert tile_dir_path == tmp_path


class TestEmitTileVerilog:
    """`_emit_tile_verilog` drives the direct tile generators."""

    @pytest.fixture
    def mock_writer(self, mocker: MockerFixture) -> MagicMock:
        return mocker.MagicMock()

    def test_regular_tile_emits_switch_matrix_config_mem_and_tile(
        self, mock_writer: MagicMock, mocker: MockerFixture, tmp_path: Path
    ) -> None:
        from fabulous.fabric_definition.tile import Tile

        tile_dir: Path = tmp_path / "LUT4AB"
        tile_dir.mkdir()
        mock_tile: MagicMock = mocker.MagicMock(spec=Tile)
        mock_tile.name = "LUT4AB"

        actual_paths: list[Path] = []
        gen_sm = mocker.patch.object(plugin_tile_flow, "genTileSwitchMatrix")
        gen_sm.side_effect = lambda *_args, **_kwargs: actual_paths.append(
            mock_writer.outFileName
        )
        gen_cm = mocker.patch.object(plugin_tile_flow, "generateConfigMem")
        gen_cm.side_effect = lambda *_args, **_kwargs: actual_paths.append(
            mock_writer.outFileName
        )
        gen_tile = mocker.patch.object(plugin_tile_flow, "generateTile")
        gen_tile.side_effect = lambda *_args, **_kwargs: actual_paths.append(
            mock_writer.outFileName
        )
        mocker.patch.object(
            plugin_tile_flow,
            "get_context",
            return_value=mocker.MagicMock(switch_matrix_debug_signal=False),
        )

        _emit_tile_verilog(
            mock_writer,
            mock_tile,
            tile_dir,
            config_bit_mode=ConfigBitMode.FLIPFLOP_CHAIN,
            multiplexer_style=MultiplexerStyle.GENERIC,
        )

        expected: list[Path] = [
            tile_dir / "LUT4AB_switch_matrix.v",
            tile_dir / "LUT4AB_ConfigMem.v",
            tile_dir / "LUT4AB.v",
        ]
        assert actual_paths == expected
        # Config-bit mode and mux style flow through instead of being hard-coded.
        gen_sm.assert_called_once_with(
            mock_writer,
            mock_tile,
            False,
            config_bit_mode=ConfigBitMode.FLIPFLOP_CHAIN,
            multiplexer_style=MultiplexerStyle.GENERIC,
            default_pip_delay=80,
        )
        gen_cm.assert_called_once_with(
            mock_writer,
            mock_tile.name,
            mock_tile.globalConfigBits,
            tile_dir / "LUT4AB_ConfigMem.csv",
        )
        gen_tile.assert_called_once_with(
            mock_writer,
            mock_tile,
            disable_user_clk=True,
            config_bit_mode=ConfigBitMode.FLIPFLOP_CHAIN,
        )

    def test_supertile_emits_per_subtile_then_wrapper(
        self, mock_writer: MagicMock, mocker: MockerFixture, tmp_path: Path
    ) -> None:
        from fabulous.fabric_definition.supertile import SuperTile
        from fabulous.fabric_definition.tile import Tile

        tile_dir: Path = tmp_path / "DSP"
        tile_dir.mkdir()
        top_dir = tile_dir / "DSP_top"
        bot_dir = tile_dir / "DSP_bot"
        top_dir.mkdir()
        bot_dir.mkdir()
        top_tile: MagicMock = mocker.MagicMock(spec=Tile)
        top_tile.name = "DSP_top"
        top_tile.tileDir = top_dir / "DSP_top.csv"
        bot_tile: MagicMock = mocker.MagicMock(spec=Tile)
        bot_tile.name = "DSP_bot"
        bot_tile.tileDir = bot_dir / "DSP_bot.csv"
        mock_supertile: MagicMock = mocker.MagicMock(spec=SuperTile)
        mock_supertile.name = "DSP"
        mock_supertile.tiles = [top_tile, bot_tile]

        emit_regular = mocker.patch.object(
            plugin_tile_flow,
            "_emit_regular_tile_verilog",
        )
        gen_super = mocker.patch.object(plugin_tile_flow, "generateSuperTile")

        _emit_tile_verilog(
            mock_writer,
            mock_supertile,
            tile_dir,
            config_bit_mode=ConfigBitMode.FLIPFLOP_CHAIN,
            multiplexer_style=MultiplexerStyle.GENERIC,
        )

        # Each sub-tile is emitted into its own directory, then the wrapper.
        assert emit_regular.call_args_list == [
            mocker.call(
                mock_writer,
                top_tile,
                top_dir,
                ConfigBitMode.FLIPFLOP_CHAIN,
                MultiplexerStyle.GENERIC,
            ),
            mocker.call(
                mock_writer,
                bot_tile,
                bot_dir,
                ConfigBitMode.FLIPFLOP_CHAIN,
                MultiplexerStyle.GENERIC,
            ),
        ]
        assert mock_writer.outFileName == tile_dir / "DSP.v"
        gen_super.assert_called_once_with(
            mock_writer,
            mock_supertile,
            disable_user_clk=True,
            config_bit_mode=ConfigBitMode.FLIPFLOP_CHAIN,
        )


@pytest.mark.usefixtures("mock_config_load")
class TestFABulousTileRunAdapter:
    """Integration-style test of `FABulousTile.run()` with heavy mocking.

    Verifies the adapter ordering: the tile is parsed, tile Verilog is emitted,
    the IO pin YAML is generated, and the config
    is populated with the keys the downstream pipeline expects before the
    inherited `SequentialFlow.run` is invoked.
    """

    @pytest.fixture
    def project_tree(self, tmp_path: Path) -> dict[str, Path]:
        project: Path = tmp_path / "proj"
        tile_dir: Path = project / "Tile" / "LUT4AB"
        tile_dir.mkdir(parents=True)
        return {"project": project, "tile_dir": tile_dir}

    def test_run_populates_config_and_delegates(
        self,
        mocker: MockerFixture,
        tmp_path: Path,
        project_tree: dict[str, Path],
    ) -> None:
        """Parse, emit and pin-YAML generation are driven from the config, and
        the downstream keys are set before `SequentialFlow.run` is invoked."""
        from fabulous.fabric_definition.tile import Tile

        tile_dir: Path = project_tree["tile_dir"]
        bel_src: Path = tmp_path / "primitives" / "LC.v"
        # Only the tile top-level exists on disk; the switch matrix and config
        # memory were "not generated", so they must not reach VERILOG_FILES.
        (tile_dir / "LUT4AB.v").write_text("", encoding="utf-8")
        mock_tile: MagicMock = mocker.MagicMock(spec=Tile)
        mock_tile.get_min_die_area.return_value = (Decimal(10), Decimal(20))
        mock_tile.name = "LUT4AB"
        mock_tile.tileDir = tile_dir / "LUT4AB.csv"
        mock_tile.bels = [mocker.MagicMock(src=bel_src), mocker.MagicMock(src=bel_src)]
        mock_tile.globalConfigBits = 0

        init_ctx = mocker.patch.object(plugin_tile_flow, "init_context")
        mocker.patch.object(
            plugin_tile_flow,
            "get_context",
            return_value=mocker.MagicMock(models_pack=None),
        )
        writer_cls = mocker.patch.object(plugin_tile_flow, "VerilogCodeGenerator")
        parse_tile = mocker.patch.object(
            plugin_tile_flow, "parse_tile_from_dir", return_value=mock_tile
        )
        emit_verilog = mocker.patch.object(plugin_tile_flow, "_emit_tile_verilog")
        gen_pin_yaml = mocker.patch.object(
            plugin_tile_flow, "generate_IO_pin_order_config"
        )
        mocker.patch.object(
            plugin_tile_flow, "get_pitch", return_value=(Decimal(1), Decimal(1))
        )
        mocker.patch.object(
            plugin_tile_flow, "get_routing_obstructions", return_value=[]
        )
        mocker.patch.object(
            plugin_tile_flow,
            "round_die_area",
            side_effect=lambda cfg: cfg,
        )

        flow = FABulousTile(
            config={
                "DESIGN_NAME": "LUT4AB",
                "FABULOUS_TILE_DIR": [str(tile_dir)],
                "FABULOUS_EXTERNAL_SIDE": "E",
                "DESIGN_DIR": str(tile_dir),
            },
            design_dir=str(tile_dir),
            pdk="sky130A",
            pdk_root=str(tmp_path / "pdk"),
        )

        flow.run_dir = str(tmp_path / "run")
        Path(flow.run_dir).mkdir()
        # Stub out the underlying `SequentialFlow.run` so we only assert on
        # the adapter's config manipulation.
        sentinel_state = mocker.MagicMock()
        super_run = mocker.patch(
            "fabulous.fabric_generator.gds_generator.flows.plugin_tile_flow.SequentialFlow.run",
            return_value=(sentinel_state, []),
        )
        initial_state = mocker.MagicMock()

        state, steps = flow.run(initial_state=initial_state)

        assert (state, steps) == (sentinel_state, [])
        # init_context is called in api_mode — no project dir required.
        init_ctx.assert_called_once_with(api_mode=True)
        parse_tile.assert_called_once_with(tile_dir, "LUT4AB", False)
        # Config-bit mode and mux style come from the declared Variable defaults.
        emit_verilog.assert_called_once_with(
            writer_cls.return_value,
            mock_tile,
            tile_dir,
            config_bit_mode=ConfigBitMode.FRAME_BASED,
            multiplexer_style=MultiplexerStyle.CUSTOM,
        )
        pin_yaml: Path = Path(flow.run_dir) / "LUT4AB_io_pin_order.yaml"
        gen_pin_yaml.assert_called_once_with(
            mock_tile, pin_yaml, external_port_side=Side.EAST
        )
        assert {
            key: flow.config[key]
            for key in (
                "DESIGN_NAME",
                "VERILOG_FILES",
                "FABULOUS_IO_PIN_ORDER_CFG",
                "FABULOUS_TILE_LOGICAL_WIDTH",
                "FABULOUS_TILE_LOGICAL_HEIGHT",
                "FABULOUS_OPT_MODE",
                "DIE_AREA",
            )
        } == {
            "DESIGN_NAME": "LUT4AB",
            "VERILOG_FILES": [str(bel_src), str(tile_dir / "LUT4AB.v")],
            "FABULOUS_IO_PIN_ORDER_CFG": str(pin_yaml),
            "FABULOUS_TILE_LOGICAL_WIDTH": 1,
            "FABULOUS_TILE_LOGICAL_HEIGHT": 1,
            "FABULOUS_OPT_MODE": OptMode.NO_OPT,
            "DIE_AREA": (0, 0, Decimal(10), Decimal(20)),
        }
        super_run.assert_called_once_with(initial_state)

    def test_run_raises_on_bad_tile_dir(
        self, mocker: MockerFixture, tmp_path: Path
    ) -> None:
        flow = FABulousTile(
            config={
                "DESIGN_NAME": "LUT4AB",
                "FABULOUS_TILE_DIR": [str(tmp_path / "does_not_exist")],
                "DESIGN_DIR": str(tmp_path),
            },
            design_dir=str(tmp_path),
            pdk="sky130A",
            pdk_root=str(tmp_path / "pdk"),
        )
        with pytest.raises(FlowException, match="is not a directory"):
            flow.run(initial_state=mocker.MagicMock())

    def test_run_uses_get_super_tile_when_supertile_flag_set(
        self,
        mocker: MockerFixture,
        tmp_path: Path,
        project_tree: dict[str, Path],
    ) -> None:
        from decimal import Decimal

        from fabulous.fabric_definition.supertile import SuperTile

        tile_dir: Path = project_tree["tile_dir"]
        (tile_dir / "DSP_top").mkdir()

        mock_tile: MagicMock = mocker.MagicMock(spec=SuperTile)
        mock_tile.max_width = 4
        mock_tile.max_height = 2
        mock_tile.get_min_die_area.return_value = (Decimal(10), Decimal(10))
        mock_tile.name = "LUT4AB"
        mock_tile.tiles = []
        mock_tile.bels = []

        mocker.patch.object(plugin_tile_flow, "init_context")
        mocker.patch.object(
            plugin_tile_flow,
            "get_context",
            return_value=mocker.MagicMock(models_pack=None),
        )
        mocker.patch.object(plugin_tile_flow, "VerilogCodeGenerator")
        parse_tile = mocker.patch.object(
            plugin_tile_flow, "parse_tile_from_dir", return_value=mock_tile
        )
        mocker.patch.object(plugin_tile_flow, "_emit_tile_verilog")
        mocker.patch.object(plugin_tile_flow, "generate_IO_pin_order_config")
        mocker.patch.object(
            plugin_tile_flow, "get_pitch", return_value=(Decimal(1), Decimal(1))
        )
        mocker.patch.object(
            plugin_tile_flow, "get_routing_obstructions", return_value=[]
        )
        mocker.patch.object(
            plugin_tile_flow, "round_die_area", side_effect=lambda cfg: cfg
        )
        mocker.patch(
            "fabulous.fabric_generator.gds_generator.flows.plugin_tile_flow.SequentialFlow.run",
            return_value=(mocker.MagicMock(), []),
        )

        flow = FABulousTile(
            config={
                "DESIGN_NAME": "LUT4AB",
                "FABULOUS_TILE_DIR": [str(tile_dir)],
                "FABULOUS_SUPERTILE": True,
                "DESIGN_DIR": str(tile_dir),
            },
            design_dir=str(tile_dir),
            pdk="sky130A",
            pdk_root=str(tmp_path / "pdk"),
        )

        flow.run_dir = str(tmp_path / "run2")
        Path(flow.run_dir).mkdir()
        flow.run(initial_state=mocker.MagicMock())

        parse_tile.assert_called_once_with(tile_dir, "LUT4AB", True)
        # Supertile logical dimensions must be taken from the tile itself.
        assert flow.config["FABULOUS_TILE_LOGICAL_WIDTH"] == 4
        assert flow.config["FABULOUS_TILE_LOGICAL_HEIGHT"] == 2


SYNTHETIC_TILE_NAME = "PLUGIN_TEST_TILE"


def _build_synthetic_tile(parent: Path) -> Path:
    """Build a minimal valid plugin-tile workspace under `parent`.

    Produces `<parent>/<name>/<name>.csv` and the matching
    `<name>_switch_matrix.list`. The trailing comma on each line keeps the
    `temp[6]` lookup in :func:`parseTilesCSV` safe.
    """
    name = SYNTHETIC_TILE_NAME
    tile_dir = parent / name
    tile_dir.mkdir()
    (tile_dir / f"{name}.csv").write_text(
        f"TILE,{name},\n"
        "NORTH,NULL,0,-1,N1END,4,\n"
        "SOUTH,S1BEG,0,1,NULL,4,\n"
        f"MATRIX,./{name}_switch_matrix.list,\n"
        "EndTILE,\n",
        encoding="utf-8",
    )
    (tile_dir / f"{name}_switch_matrix.list").write_text(
        "S1BEG[0|1|2|3],N1END[3|2|1|0]\n",
        encoding="utf-8",
    )
    return tile_dir


@pytest.mark.usefixtures("mock_config_load")
class TestFABulousTileEndToEnd:
    """End-to-end exercise of `FABulousTile.run()` against a synthetic tile.

    Unlike :class:`TestFABulousTileRunAdapter`, this class does not mock the
    plugin's prep work (CSV parsing, RTL emission, pin-YAML generation): it
    runs the real generators on disk. Only the PDK-reading helpers and the
    inherited `SequentialFlow.run` are stubbed, so we cover regressions in
    the plugin's actual code path without needing a PDK install or EDA tools.

    The tile workspace is generated programmatically inside `tmp_path` so
    the test does not depend on any in-tree demo plugin tile.
    """

    @pytest.fixture
    def tile_workspace(self, tmp_path: Path) -> Path:
        return _build_synthetic_tile(tmp_path)

    def test_run_emits_real_rtl_and_pin_yaml(
        self,
        tile_workspace: Path,
        tmp_path: Path,
        mocker: MockerFixture,
    ) -> None:
        """Run the plugin against a synthetic tile and verify on-disk artifacts.

        Only PDK-touching helpers are stubbed; the generators, parser, and
        pin-YAML producer all execute. This is the test that would have
        caught the `FABulous_API.fabric` AttributeError surfaced by the
        librelane CLI smoke run.
        """
        # Stub PDK readers; plugin computes a fake DIE_AREA from these.
        mocker.patch.object(
            plugin_tile_flow, "get_pitch", return_value=(Decimal(1), Decimal(1))
        )
        mocker.patch.object(
            plugin_tile_flow, "get_routing_obstructions", return_value=[]
        )
        mocker.patch.object(plugin_tile_flow, "round_die_area", side_effect=lambda c: c)
        # Don't actually run the LibreLane SequentialFlow steps.
        mocker.patch(
            "fabulous.fabric_generator.gds_generator.flows.plugin_tile_flow.SequentialFlow.run",
            return_value=(mocker.MagicMock(), []),
        )

        name = SYNTHETIC_TILE_NAME
        flow = FABulousTile(
            config={
                "DESIGN_NAME": name,
                "FABULOUS_TILE_DIR": [str(tile_workspace)],
                "VERILOG_FILES": [],
                "DESIGN_DIR": str(tile_workspace),
            },
            design_dir=str(tile_workspace),
            pdk="sky130A",
            pdk_root=str(tmp_path / "pdk"),
        )
        flow.run_dir = str(tmp_path / "run")
        Path(flow.run_dir).mkdir()

        flow.run(initial_state=mocker.MagicMock())

        # The plugin must have re-emitted the per-tile RTL artifacts from the
        # `.list` switch matrix, which is read directly into the model without a
        # bootstrap-CSV round trip...
        assert (tile_workspace / f"{name}.v").exists()
        assert (tile_workspace / f"{name}_switch_matrix.v").exists()
        # ...and produced the IO pin-order YAML in the run directory.
        pin_yaml = Path(flow.run_dir) / f"{name}_io_pin_order.yaml"
        assert pin_yaml.exists()
        # And the downstream-facing config keys must be set.
        assert flow.config["DESIGN_NAME"] == name
        assert flow.config["FABULOUS_IO_PIN_ORDER_CFG"] == str(pin_yaml)
        assert flow.config["FABULOUS_TILE_LOGICAL_WIDTH"] == 1
        assert flow.config["FABULOUS_TILE_LOGICAL_HEIGHT"] == 1
        # Generated RTL must be in VERILOG_FILES so downstream synth picks it up.
        # The 1:1 switch matrix needs no config bits, so no ConfigMem is
        # emitted and none is listed.
        tile_dir: Path = tile_workspace.resolve()
        assert flow.config["VERILOG_FILES"] == [
            str(tile_dir / f"{name}.v"),
            str(tile_dir / f"{name}_switch_matrix.v"),
        ]
