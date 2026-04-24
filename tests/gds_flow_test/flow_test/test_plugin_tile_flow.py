"""Tests for the ``FABulousTile`` LibreLane-plugin adapter.

These tests verify the *adapting* layer: how ``FABulousTile`` translates
plugin-level config variables and tile-directory inputs into what the
underlying :class:`FABulousTileVerilogMacroFlow` pipeline expects. They do not
exercise the real LibreLane pipeline (that is covered elsewhere).
"""

# ruff: noqa: SLF001

import shutil
from decimal import Decimal
from pathlib import Path
from unittest.mock import MagicMock

import pytest
from librelane.flows.flow import Flow, FlowException
from pytest_mock import MockerFixture

from fabulous.fabric_generator.gds_generator.flows import plugin_tile_flow
from fabulous.fabric_generator.gds_generator.flows.plugin_tile_flow import (
    FABulousTile,
    _emit_tile_verilog,
)
from fabulous.fabric_generator.gds_generator.flows.tile_macro_flow import (
    FABulousTileVerilogMacroFlow,
)


class TestFABulousTileSchema:
    """Schema-level assertions for the plugin wrapper."""

    def test_registered_in_flow_factory(self) -> None:
        """LibreLane must be able to resolve the flow by name."""
        assert Flow.factory.get("FABulousTile") is FABulousTile

    def test_exposes_plugin_config_vars(self) -> None:
        """The three plugin-level variables must be declared."""
        names: set[str] = {v.name for v in FABulousTile.config_vars}
        assert {
            "FABULOUS_TILE_DIR",
            "FABULOUS_EXTERNAL_SIDE",
            "FABULOUS_SUPERTILE",
        } <= names

    def test_inherits_underlying_config_vars(self) -> None:
        """Underlying flow's config vars must still be declared so LibreLane validates
        the full schema against a single class."""
        plugin_names: set[str] = {v.name for v in FABulousTile.config_vars}
        underlying_names: set[str] = {
            v.name for v in FABulousTileVerilogMacroFlow.config_vars
        }
        assert underlying_names <= plugin_names

    def test_inherits_steps_from_underlying_flow(self) -> None:
        """``Steps`` matches the underlying flow (SequentialFlow may copy)."""
        assert FABulousTile.Steps == FABulousTileVerilogMacroFlow.Steps

    def test_inherits_gating_config_vars(self) -> None:
        """Gating vars come from the underlying flow unchanged."""
        assert (
            FABulousTile.gating_config_vars
            == FABulousTileVerilogMacroFlow.gating_config_vars
        )

    def test_fabulous_supertile_default_false(self) -> None:
        """Default for FABULOUS_SUPERTILE is ``False`` so users can omit it."""
        var = next(
            v for v in FABulousTile.config_vars if v.name == "FABULOUS_SUPERTILE"
        )
        assert var.default is False

    def test_fabulous_io_pin_order_cfg_is_optional_on_step(self) -> None:
        """``FABULOUS_IO_PIN_ORDER_CFG`` must be optional on the step.

        The FABulous IO placer is fully automated: the plugin generates the
        pin-order YAML inside ``run()`` and users of the plugin should never
        have to set this variable by hand. If the step declares the variable
        as required without a default, LibreLane's ``Config.load`` rejects
        any mole99-style ``config.yaml`` before ``run()`` can supply a real
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
        """``FABULOUS_TILE_DIR`` must validate when set to ``dir::...``.

        LibreLane rewrites ``dir::.`` to ``refg::$DESIGN_DIR/.`` and the refg
        resolver always produces a ``list[str]`` (see
        ``librelane/config/preprocessor.py``). If the Variable is typed as a
        scalar ``Path`` the type validator crashes with
        ``TypeError: argument should be ... not 'list'`` before ``run()`` ever
        executes, making ``dir::.`` unusable for this variable.
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
    """``_emit_tile_verilog`` drives the direct tile generators."""

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

        _emit_tile_verilog(mock_writer, mock_tile, tile_dir)

        expected: list[Path] = [
            tile_dir / "LUT4AB_switch_matrix.v",
            tile_dir / "LUT4AB_ConfigMem.v",
            tile_dir / "LUT4AB.v",
        ]
        assert actual_paths == expected
        gen_sm.assert_called_once()
        gen_cm.assert_called_once_with(
            mock_writer, mock_tile, tile_dir / "LUT4AB_ConfigMem.csv"
        )
        gen_tile.assert_called_once()

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

        _emit_tile_verilog(mock_writer, mock_supertile, tile_dir)

        assert [call.args[2] for call in emit_regular.call_args_list] == [
            top_dir,
            bot_dir,
        ]
        assert mock_writer.outFileName == tile_dir / "DSP.v"
        gen_super.assert_called_once()


@pytest.mark.usefixtures("mock_config_load")
class TestFABulousTileRunAdapter:
    """Integration-style test of ``FABulousTile.run()`` with heavy mocking.

    Verifies the adapter ordering: the tile is parsed, tile Verilog is emitted,
    the IO pin YAML is generated, and the config
    is populated with the keys the downstream pipeline expects before the
    inherited ``SequentialFlow.run`` is invoked.
    """

    @pytest.fixture
    def project_tree(self, tmp_path: Path) -> dict[str, Path]:
        project: Path = tmp_path / "proj"
        tile_dir: Path = project / "Tile" / "LUT4AB"
        tile_dir.mkdir(parents=True)
        # Existing Verilog discovered via ``**/*.v`` glob on the project Tile dir.
        (tile_dir.parent / "shared.v").write_text("", encoding="utf-8")
        return {"project": project, "tile_dir": tile_dir}

    def test_run_populates_config_and_delegates(
        self,
        mocker: MockerFixture,
        tmp_path: Path,
        project_tree: dict[str, Path],
    ) -> None:
        from decimal import Decimal

        from librelane.config.config import Config

        from fabulous.fabric_definition.tile import Tile

        tile_dir: Path = project_tree["tile_dir"]
        mock_tile: MagicMock = mocker.MagicMock(spec=Tile)
        mock_tile.get_min_die_area.return_value = (Decimal(10), Decimal(10))
        mock_tile.name = "LUT4AB"
        mock_tile.tileDir = tile_dir / "LUT4AB.csv"
        mock_tile.bels = []
        mock_tile.globalConfigBits = 0

        init_ctx = mocker.patch.object(plugin_tile_flow, "init_context")
        mocker.patch.object(
            plugin_tile_flow,
            "get_context",
            return_value=mocker.MagicMock(models_pack=None),
        )
        mocker.patch.object(plugin_tile_flow, "VerilogCodeGenerator")
        parse_tile = mocker.patch.object(
            plugin_tile_flow, "_parse_plugin_tile", return_value=mock_tile
        )
        emit_verilog = mocker.patch.object(plugin_tile_flow, "_emit_tile_verilog")
        gen_pin_yaml = mocker.patch.object(
            plugin_tile_flow, "generate_IO_pin_order_config"
        )
        mocker.patch.object(
            plugin_tile_flow, "get_pitch", return_value=(Decimal(1), Decimal(1))
        )
        mocker.patch.object(plugin_tile_flow, "get_offset")
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
                "DESIGN_DIR": str(tile_dir),
            },
            design_dir=str(tile_dir),
            pdk="sky130A",
            pdk_root=str(tmp_path / "pdk"),
        )

        flow.run_dir = str(tmp_path / "run")
        Path(flow.run_dir).mkdir()
        # Stub out the underlying ``SequentialFlow.run`` so we only assert on
        # the adapter's config manipulation.
        sentinel_state = mocker.MagicMock()
        super_run = mocker.patch(
            "fabulous.fabric_generator.gds_generator.flows.plugin_tile_flow.SequentialFlow.run",
            return_value=(sentinel_state, []),
        )

        state, steps = flow.run(initial_state=mocker.MagicMock())

        assert (state, steps) == (sentinel_state, [])
        # init_context is called in api_mode — no project dir required.
        init_ctx.assert_called_once_with(api_mode=True)
        parse_tile.assert_called_once_with(tile_dir, "LUT4AB", False)
        emit_verilog.assert_called_once()
        # Pin YAML should be generated below run_dir.
        assert gen_pin_yaml.call_count == 1
        assert gen_pin_yaml.call_args.args[:2] == (
            mock_tile,
            Path(flow.run_dir) / "LUT4AB_io_pin_order.yaml",
        )
        # Adapter must set the downstream keys.
        assert flow.config["DESIGN_NAME"] == "LUT4AB"
        assert flow.config["FABULOUS_TILE_LOGICAL_WIDTH"] == 1
        assert flow.config["FABULOUS_TILE_LOGICAL_HEIGHT"] == 1
        assert str(flow.config["FABULOUS_IO_PIN_ORDER_CFG"]).endswith(
            "LUT4AB_io_pin_order.yaml"
        )
        assert isinstance(flow.config, Config)
        super_run.assert_called_once()

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
            plugin_tile_flow, "_parse_plugin_tile", return_value=mock_tile
        )
        mocker.patch.object(plugin_tile_flow, "_emit_tile_verilog")
        mocker.patch.object(plugin_tile_flow, "generate_IO_pin_order_config")
        mocker.patch.object(
            plugin_tile_flow, "get_pitch", return_value=(Decimal(1), Decimal(1))
        )
        mocker.patch.object(plugin_tile_flow, "get_offset")
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


@pytest.mark.usefixtures("mock_config_load")
class TestFABulousTileEndToEnd:
    """End-to-end exercise of ``FABulousTile.run()`` against a real demo tile.

    Unlike :class:`TestFABulousTileRunAdapter`, this class does not mock the
    plugin's prep work (CSV parsing, RTL emission, pin-YAML generation): it
    runs the real generators on disk. Only the PDK-reading helpers and the
    inherited ``SequentialFlow.run`` are stubbed, so we cover regressions in
    the plugin's actual code path without needing a PDK install or EDA tools.
    """

    DEMO_TILE: Path = (
        Path(__file__).resolve().parents[3] / "demo" / "Tile" / "N_term_single2"
    )

    @pytest.fixture
    def tile_workspace(self, tmp_path: Path) -> Path:
        """Copy the demo tile into ``tmp_path`` so the real generators can write
        artifacts without touching the in-tree ``demo/`` directory."""
        dst = tmp_path / "N_term_single2"
        shutil.copytree(self.DEMO_TILE, dst)
        # Strip pre-generated artifacts so we assert the plugin re-emits them.
        for stale in (
            "N_term_single2.v",
            "N_term_single2_switch_matrix.v",
            "N_term_single2_io_pin_order.yaml",
            "N_term_single2_switch_matrix.csv",
        ):
            (dst / stale).unlink(missing_ok=True)
        return dst

    def test_run_emits_real_rtl_and_pin_yaml(
        self,
        tile_workspace: Path,
        tmp_path: Path,
        mocker: MockerFixture,
    ) -> None:
        """Run the plugin against a real demo tile and verify on-disk artifacts.

        Only PDK-touching helpers are stubbed; the generators, parser, and
        pin-YAML producer all execute. This is the test that would have
        caught the ``FABulous_API.fabric`` AttributeError surfaced by the
        librelane CLI smoke run.
        """
        # Stub PDK readers; plugin computes a fake DIE_AREA from these.
        mocker.patch.object(
            plugin_tile_flow, "get_pitch", return_value=(Decimal(1), Decimal(1))
        )
        mocker.patch.object(plugin_tile_flow, "get_offset")
        mocker.patch.object(
            plugin_tile_flow, "get_routing_obstructions", return_value=[]
        )
        mocker.patch.object(plugin_tile_flow, "round_die_area", side_effect=lambda c: c)
        # Don't actually run the LibreLane SequentialFlow steps.
        mocker.patch(
            "fabulous.fabric_generator.gds_generator.flows.plugin_tile_flow.SequentialFlow.run",
            return_value=(mocker.MagicMock(), []),
        )

        flow = FABulousTile(
            config={
                "DESIGN_NAME": "N_term_single2",
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

        # The plugin must have re-emitted the per-tile RTL artifacts...
        assert (tile_workspace / "N_term_single2.v").exists()
        assert (tile_workspace / "N_term_single2_switch_matrix.v").exists()
        # ...bootstrapped the .list switch-matrix into a .csv...
        assert (tile_workspace / "N_term_single2_switch_matrix.csv").exists()
        # ...and produced the IO pin-order YAML in the run directory.
        pin_yaml = Path(flow.run_dir) / "N_term_single2_io_pin_order.yaml"
        assert pin_yaml.exists()
        # And the downstream-facing config keys must be set.
        assert flow.config["DESIGN_NAME"] == "N_term_single2"
        assert flow.config["FABULOUS_IO_PIN_ORDER_CFG"] == str(pin_yaml)
        assert flow.config["FABULOUS_TILE_LOGICAL_WIDTH"] == 1
        assert flow.config["FABULOUS_TILE_LOGICAL_HEIGHT"] == 1
        # Generated RTL must be in VERILOG_FILES so downstream synth picks it up.
        verilog_files = [str(p) for p in flow.config["VERILOG_FILES"]]
        assert any("N_term_single2.v" in p for p in verilog_files)
        assert any("N_term_single2_switch_matrix.v" in p for p in verilog_files)
