"""Tests for FABulousFabricOptimisationFlow - fabric optimisation flow.

Tests focus on:
- Flow initialization and configuration
- Project directory validation
- Worker function behavior
- Flow steps and configuration variables
"""

# ruff: noqa: SLF001

import json
from decimal import Decimal
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock

import pytest
from librelane.flows.flow import FlowError
from librelane.state.design_format import DesignFormat
from librelane.state.state import State
from pytest_mock import MockerFixture

from fabulous.fabric_definition.define import IO, HDLType, Side
from fabulous.fabric_definition.fabric import Fabric
from fabulous.fabric_definition.port import TilePort
from fabulous.fabric_generator.gds_generator.flows.fabric_optimisation_flow import (
    FABulousFabricOptimisationFlow,
    WorkerResult,
    _run_tile_flow_worker,
)
from fabulous.fabric_generator.gds_generator.steps.tile_area_opt import OptMode
from fabulous.fabulous_api import FABulous_API
from tests.conftest import make_empty_tile, make_fabric_from_grid


# Shared fixtures
@pytest.fixture
def mock_flow_with_validate_project_dir(mocker: MockerFixture) -> MagicMock:
    """Create a mock flow with _validate_project_dir method bound."""
    flow: MagicMock = mocker.MagicMock(spec=FABulousFabricOptimisationFlow)
    flow._validate_project_dir = FABulousFabricOptimisationFlow._validate_project_dir
    return flow


@pytest.fixture
def mock_fabric(mocker: MockerFixture) -> MagicMock:
    """Create a mock fabric for testing."""
    fabric: MagicMock = mocker.MagicMock()
    fabric.tileDic = {"tile1": mocker.MagicMock(), "tile2": mocker.MagicMock()}
    fabric.superTileDic = {}
    return fabric


class TestValidateProjectDir:
    """Tests for _validate_project_dir method."""

    def test_validate_project_dir_success(
        self,
        mock_flow_with_validate_project_dir: MagicMock,
        mock_fabric: MagicMock,
        tmp_path: Path,
    ) -> None:
        """Test validation passes for valid directory structure."""
        flow: MagicMock = mock_flow_with_validate_project_dir
        # Create required directories
        tile_dir: Path = tmp_path / "Tile"
        tile_dir.mkdir()
        (tile_dir / "tile1").mkdir()
        (tile_dir / "tile2").mkdir()

        # Should not raise
        flow._validate_project_dir(flow, tmp_path, mock_fabric)

    def test_validate_project_dir_missing_proj_dir(
        self,
        mock_flow_with_validate_project_dir: MagicMock,
        mock_fabric: MagicMock,
    ) -> None:
        """Test validation fails when project directory doesn't exist."""
        flow: MagicMock = mock_flow_with_validate_project_dir
        nonexistent: Path = Path("/nonexistent/path")

        with pytest.raises(FileNotFoundError, match="Project directory not found"):
            flow._validate_project_dir(flow, nonexistent, mock_fabric)

    def test_validate_project_dir_not_a_directory(
        self,
        mock_flow_with_validate_project_dir: MagicMock,
        mock_fabric: MagicMock,
        tmp_path: Path,
    ) -> None:
        """Test validation fails when path is not a directory."""
        flow: MagicMock = mock_flow_with_validate_project_dir
        file_path: Path = tmp_path / "file.txt"
        file_path.touch()

        with pytest.raises(NotADirectoryError, match="not a directory"):
            flow._validate_project_dir(flow, file_path, mock_fabric)

    def test_validate_project_dir_missing_tile_dir(
        self,
        mock_flow_with_validate_project_dir: MagicMock,
        mock_fabric: MagicMock,
        tmp_path: Path,
    ) -> None:
        """Test validation fails when Tile directory is missing."""
        flow: MagicMock = mock_flow_with_validate_project_dir
        with pytest.raises(FileNotFoundError, match="Tile directory not found"):
            flow._validate_project_dir(flow, tmp_path, mock_fabric)

    def test_validate_project_dir_missing_tiles(
        self,
        mock_flow_with_validate_project_dir: MagicMock,
        mock_fabric: MagicMock,
        tmp_path: Path,
    ) -> None:
        """Test validation fails when tile directories are missing."""
        flow: MagicMock = mock_flow_with_validate_project_dir
        tile_dir: Path = tmp_path / "Tile"
        tile_dir.mkdir()
        # Only create tile1, not tile2
        (tile_dir / "tile1").mkdir()

        with pytest.raises(FileNotFoundError) as exc_info:
            flow._validate_project_dir(flow, tmp_path, mock_fabric)

        assert str(exc_info.value) == (
            f"Missing tile directories in {tile_dir}:\n  - tile2 (regular Tile)"
        )

    def test_validate_project_dir_with_supertiles(
        self,
        mock_flow_with_validate_project_dir: MagicMock,
        mocker: MockerFixture,
        tmp_path: Path,
    ) -> None:
        """Test validation with SuperTiles."""
        flow: MagicMock = mock_flow_with_validate_project_dir
        fabric: MagicMock = mocker.MagicMock()
        fabric.tileDic = {"subtile1": mocker.MagicMock()}

        # SuperTile containing subtile1
        supertile: MagicMock = mocker.MagicMock()
        supertile.tiles = [mocker.MagicMock(name="subtile1")]
        supertile.tiles[0].name = "subtile1"
        fabric.superTileDic = {"SuperTile1": supertile}

        tile_dir: Path = tmp_path / "Tile"
        tile_dir.mkdir()
        # SubTiles don't need directories, but SuperTiles do
        (tile_dir / "SuperTile1").mkdir()

        flow._validate_project_dir(flow, tmp_path, fabric)

    def test_validate_project_dir_missing_supertile_dir(
        self,
        mock_flow_with_validate_project_dir: MagicMock,
        mocker: MockerFixture,
        tmp_path: Path,
    ) -> None:
        """Test validation fails when SuperTile directory is missing."""
        flow: MagicMock = mock_flow_with_validate_project_dir
        fabric: MagicMock = mocker.MagicMock()
        fabric.tileDic = {}

        supertile: MagicMock = mocker.MagicMock()
        supertile.tiles = []
        fabric.superTileDic = {"SuperTile1": supertile}

        tile_dir: Path = tmp_path / "Tile"
        tile_dir.mkdir()

        with pytest.raises(FileNotFoundError) as exc_info:
            flow._validate_project_dir(flow, tmp_path, fabric)

        assert str(exc_info.value) == (
            f"Missing tile directories in {tile_dir}:\n  - SuperTile1 (SuperTile)"
        )


_FLOW_MODULE = "fabulous.fabric_generator.gds_generator.flows.fabric_optimisation_flow"
_PIN_MIN_CONFIG: dict[str, Decimal] = {
    "FABULOUS_PIN_MIN_WIDTH": Decimal("10.0"),
    "FABULOUS_PIN_MIN_HEIGHT": Decimal("20.0"),
}
_PIN_MIN: dict[str, float] = {
    "fabulous__pin_min_width": 10.0,
    "fabulous__pin_min_height": 20.0,
}


def _run_worker(
    tile: MagicMock, tmp_path: Path, hdl_type: HDLType, **overrides: object
) -> WorkerResult:
    """Call the worker with fixed paths under `tmp_path`."""
    return _run_tile_flow_worker(
        tile_type=tile,
        io_pin_config=tmp_path / "io.yaml",
        optimisation=OptMode.BALANCE,
        base_config_path=tmp_path / "base.yaml",
        override_config_path=tmp_path / "override.yaml",
        pdk="test_pdk",
        pdk_root=tmp_path,
        models_pack=tmp_path / "models_pack.v",
        hdl_type=hdl_type,
        **overrides,
    )


class TestRunTileFlowWorker:
    """Tests for _run_tile_flow_worker function."""

    def test_worker_propagates_unexpected_exceptions(
        self, mocker: MockerFixture, tmp_path: Path
    ) -> None:
        """Unexpected (non-flow) exceptions propagate instead of being masked.

        Only librelane `FlowError` (which includes deferred errors raised after
        the GDS is written) triggers the disk-recovery path. A genuine bug must
        surface with its stack trace.
        """
        mocker.patch(
            f"{_FLOW_MODULE}.FABulousTileVerilogMacroFlow",
            side_effect=ValueError("Test error"),
        )

        with pytest.raises(ValueError, match="Test error"):
            _run_worker(mocker.MagicMock(), tmp_path, HDLType.VERILOG)

    def test_worker_recovers_state_on_deferred_flow_error(
        self, mocker: MockerFixture, tmp_path: Path
    ) -> None:
        """A `FlowError` after the state was saved recovers the on-disk state."""
        run_dir: Path = tmp_path / "run"
        step_dir: Path = run_dir / "42-klayout-xor"
        step_dir.mkdir(parents=True)
        (step_dir / "state_out.json").write_text(
            json.dumps({"metrics": {"design__die__bbox": "0 0 30 40"}}),
            encoding="utf-8",
        )
        mock_flow: MagicMock = mocker.MagicMock()
        mock_flow.start.side_effect = FlowError("deferred errors were encountered")
        mock_flow.run_dir = str(run_dir)
        mock_flow.config = _PIN_MIN_CONFIG
        mocker.patch(
            f"{_FLOW_MODULE}.FABulousTileVerilogMacroFlow", return_value=mock_flow
        )

        state, error_trace, pin_min = _run_worker(
            mocker.MagicMock(), tmp_path, HDLType.VERILOG
        )

        assert state is not None
        assert dict(state.metrics) == {"design__die__bbox": "0 0 30 40"}
        assert error_trace is not None
        assert error_trace.splitlines()[-1] == (
            "librelane.flows.flow.FlowError: deferred errors were encountered"
        )
        assert pin_min == _PIN_MIN

    @pytest.mark.parametrize(
        ("hdl_type", "selected", "unused"),
        [
            pytest.param(
                HDLType.VERILOG,
                "FABulousTileVerilogMacroFlow",
                "FABulousTileVHDLMacroFlow",
                id="verilog",
            ),
            pytest.param(
                HDLType.VHDL,
                "FABulousTileVHDLMacroFlow",
                "FABulousTileVerilogMacroFlow",
                id="vhdl",
            ),
        ],
    )
    def test_worker_builds_flow_and_returns_state(
        self,
        mocker: MockerFixture,
        tmp_path: Path,
        hdl_type: HDLType,
        selected: str,
        unused: str,
    ) -> None:
        """The HDL picks the tile flow, which gets every argument and override."""
        mock_state: MagicMock = mocker.MagicMock()
        mock_flow: MagicMock = mocker.MagicMock()
        mock_flow.start.return_value = mock_state
        mock_flow.config = _PIN_MIN_CONFIG
        selected_cls: MagicMock = mocker.patch(
            f"{_FLOW_MODULE}.{selected}", return_value=mock_flow
        )
        unused_cls: MagicMock = mocker.patch(f"{_FLOW_MODULE}.{unused}")
        tile: MagicMock = mocker.MagicMock()

        result: WorkerResult = _run_worker(
            tile, tmp_path, hdl_type, CUSTOM_KEY="custom_value"
        )

        assert result == (mock_state, None, _PIN_MIN)
        selected_cls.assert_called_once_with(
            tile,
            tmp_path / "io.yaml",
            OptMode.BALANCE,
            pdk="test_pdk",
            pdk_root=tmp_path,
            models_pack_path=tmp_path / "models_pack.v",
            base_config_path=tmp_path / "base.yaml",
            override_config_path=tmp_path / "override.yaml",
            design_dir=None,
            CUSTOM_KEY="custom_value",
        )
        unused_cls.assert_not_called()


def _logged_tokens(info_mock: MagicMock) -> list[list[str]]:
    """Split every logged line into tokens so column padding does not matter."""
    return [str(call.args[0]).split() for call in info_mock.call_args_list]


class TestLogNlpSummary:
    """Tests for the _log_nlp_summary static method."""

    @pytest.mark.parametrize(
        ("metrics", "rows", "total"),
        [
            pytest.param(
                {
                    # nlp__tile__area maps name -> (x0, y0, width, height).
                    "nlp__tile__area": {
                        "tile1": (0, 0, 10.0, 20.0),
                        "tile2": (0, 0, 5.0, 4.0),
                    },
                    "nlp__tile__stdcell_area": {"tile1": 100.0, "tile2": 5.0},
                    "nlp__total__area": 220.0,
                },
                [
                    ["tile1", "10.00", "20.00", "200.00", "50.0%"],
                    ["tile2", "5.00", "4.00", "20.00", "25.0%"],
                ],
                "220.0",
                id="utilisation",
            ),
            pytest.param(
                {
                    "nlp__tile__area": {"empty": (0, 0, 0.0, 0.0)},
                    "nlp__tile__stdcell_area": {"empty": 0.0},
                    "nlp__total__area": 0,
                },
                [["empty", "0.00", "0.00", "0.00", "0.0%"]],
                "0",
                id="zero_area_is_zero_util",
            ),
        ],
    )
    def test_logs_table(
        self,
        mocker: MockerFixture,
        metrics: dict[str, object],
        rows: list[list[str]],
        total: str,
    ) -> None:
        """One row per tile: width, height, allocated area and utilisation."""
        info_mock: MagicMock = mocker.patch(f"{_FLOW_MODULE}.info")
        nlp_state: MagicMock = mocker.MagicMock()
        nlp_state.metrics = metrics

        FABulousFabricOptimisationFlow._log_nlp_summary(nlp_state)

        rule: list[str] = ["-" * 64]
        assert _logged_tokens(info_mock) == [
            ["Tile", "Width", "Height", "Area", "Util"],
            rule,
            *rows,
            rule,
            ["Total", "fabric", "area", total],
        ]


class TestRunNlpOnlyEarlyReturn:
    """Tests for the FABULOUS_NLP_ONLY early-return path in run()."""

    def test_returns_after_nlp_without_stitching(
        self, mocker: MockerFixture, tmp_path: Path
    ) -> None:
        """With FABULOUS_NLP_ONLY set, run() returns the NLP state and stops.

        The heavy recompilation/stitching collaborators must not be invoked:
        no process pool, no stitching flow.
        """
        flow: MagicMock = mocker.MagicMock(spec=FABulousFabricOptimisationFlow)

        fabric: MagicMock = mocker.MagicMock()

        # Drive config lookups from a real dict so behaviour is explicit.
        # TILE_OPT_INFO present -> initial compilation is skipped.
        config_data: dict[str, object] = {
            "FABULOUS_PROJ_DIR": str(tmp_path),
            "TILE_OPT_INFO": str(tmp_path / "summary.json"),
            "FABULOUS_NLP_ONLY": True,
        }
        config: MagicMock = mocker.MagicMock()
        config.__getitem__.side_effect = config_data.__getitem__
        config.get.side_effect = config_data.get
        config.copy.return_value = config
        flow.config = config
        # The fabric reaches run() as a flow attribute, not through the config.
        flow.fabric = fabric

        # progress_bar is an instance attribute on Flow, not a class attribute,
        # so the spec'd mock won't auto-create it.
        flow.progress_bar = mocker.MagicMock()

        nlp_state: MagicMock = mocker.MagicMock()
        flow.start_step.return_value = nlp_state
        flow._validate_project_dir = mocker.MagicMock()
        flow._init_compile = mocker.MagicMock()
        flow._log_nlp_summary = mocker.MagicMock()

        # Patch the collaborators constructed inside run().
        nlp_step = mocker.patch(
            "fabulous.fabric_generator.gds_generator.flows."
            "fabric_optimisation_flow.FabricAreaOptimisation"
        )
        stitching = mocker.patch(
            "fabulous.fabric_generator.gds_generator.flows."
            "fabric_optimisation_flow.FABulousFabricMacroFlow"
        )
        pool = mocker.patch(
            "fabulous.fabric_generator.gds_generator.flows."
            "fabric_optimisation_flow.DillProcessPoolExecutor"
        )

        initial_state: MagicMock = mocker.MagicMock()
        result_state, result_steps = FABulousFabricOptimisationFlow.run(
            flow, initial_state
        )

        assert nlp_step.call_args.kwargs["fabric"] is fabric
        # NLP-only contract: returns the NLP state with no executed steps.
        assert result_state is nlp_state
        assert result_steps == []
        # NLP summary is logged on the early-return path.
        flow._log_nlp_summary.assert_called_once_with(nlp_state)
        # Step 1 skipped because TILE_OPT_INFO was provided.
        flow._init_compile.assert_not_called()
        # No recompilation pool, no stitching flow.
        pool.assert_not_called()
        stitching.assert_not_called()


class TestFinaliseFabric:
    """Tests for the post-stitching completeness check and summary."""

    def test_raises_when_no_gds(self) -> None:
        """An incomplete stitch (no GDS) raises rather than reporting success."""
        fabric: Fabric = make_fabric_from_grid([[make_empty_tile("LUT")]])

        with pytest.raises(RuntimeError, match="no GDS"):
            FABulousFabricOptimisationFlow._finalise(fabric, State(), {})

    def test_logs_summary_with_per_tile_macro_sizes(
        self, mocker: MockerFixture
    ) -> None:
        """A complete stitch logs the die area and each tile macro's size."""
        fabric: Fabric = make_fabric_from_grid(
            [[make_empty_tile("LUT"), make_empty_tile("DSP")]]
        )
        fabric.name = "myfab"
        final_state = State(
            {DesignFormat.GDS: "/runs/final/gds/myfab.gds"},
            metrics={"design__die__bbox": "0 0 100 200"},
        )
        tile_states: dict[str, State] = {
            "LUT": State(metrics={"design__die__bbox": "0 0 30 40"}),
            "DSP": State(metrics={"design__die__bbox": "0 0 50 60"}),
        }
        info_mock: MagicMock = mocker.patch(f"{_FLOW_MODULE}.info")

        FABulousFabricOptimisationFlow._finalise(fabric, final_state, tile_states)

        assert _logged_tokens(info_mock) == [
            ["===", "Fabric", "summary", "==="],
            ["Fabric", ":", "myfab"],
            ["Unique", "tile", "types", ":", "2"],
            ["Die", "area", ":", "100.00", "x", "200.00", "um"],
            ["Tile", "macro", "sizes:"],
            ["DSP", "50.00", "x", "60.00", "um"],
            ["LUT", "30.00", "x", "40.00", "um"],
        ]


def _fabric_with_real_ports() -> Fabric:
    """A real one-tile fabric whose tile carries a real `TilePort`.

    `TilePort` is the model class librelane's JSON encoder cannot handle, so a
    fabric without one would not reproduce the serialisation failure.
    """
    tile = make_empty_tile(
        "LUT4AB",
        ports=[
            TilePort(
                name="N1BEG",
                io_direction=IO.OUTPUT,
                width=1,
                side_of_tile=Side.NORTH,
            )
        ],
    )
    return make_fabric_from_grid([[tile]])


@pytest.mark.usefixtures("mock_config_load")
class TestFabricStaysOutOfTheConfig:
    """The fabric model reaches the flow as an argument, not a config variable.

    librelane serialises every config value into `resolved.json` at the start of
    `Flow.start`, and its encoder only understands dataclasses. A `Fabric` holds
    `TilePort` objects, which are not dataclasses, so putting the model in the
    config aborts the run before the first step.
    """

    def _flow(
        self, fabric: Fabric, mock_pdk_root: dict[str, Any], tmp_path: Path
    ) -> FABulousFabricOptimisationFlow:
        return FABulousFabricOptimisationFlow(
            [{"FABULOUS_PROJ_DIR": str(tmp_path), "DESIGN_NAME": fabric.name}],
            fabric=fabric,
            name=fabric.name,
            design_dir=str(tmp_path / "macro"),
            pdk=mock_pdk_root["pdk"],
            pdk_root=str(mock_pdk_root["pdk_root"]),
        )

    def test_flow_holds_the_fabric_outside_its_config(
        self, mock_pdk_root: dict[str, Any], tmp_path: Path
    ) -> None:
        """The flow exposes the fabric it was given and keeps it out of the config."""
        fabric: Fabric = _fabric_with_real_ports()

        flow: FABulousFabricOptimisationFlow = self._flow(
            fabric, mock_pdk_root, tmp_path
        )

        assert flow.fabric is fabric
        assert all(value is not fabric for value in flow.config.values())

    def test_config_survives_the_resolved_json_dump(
        self, mock_pdk_root: dict[str, Any], tmp_path: Path
    ) -> None:
        """`Flow.start` dumps the config to JSON, so every value must serialise."""
        flow: FABulousFabricOptimisationFlow = self._flow(
            _fabric_with_real_ports(), mock_pdk_root, tmp_path
        )

        json.loads(flow.config.dumps())


@pytest.mark.usefixtures("mock_config_load")
class TestFullFabricAutomationConfig:
    """The config `full_fabric_automation` composes is the one that must dump.

    The flow-level tests pin the contract; this one covers the call site that
    builds the config, where an unencodable value would be reintroduced.
    """

    def test_composed_config_survives_the_resolved_json_dump(
        self, mocker: MockerFixture, mock_pdk_root: dict[str, Any], tmp_path: Path
    ) -> None:
        """The config the API hands the flow serialises when `start` dumps it."""
        api: FABulous_API = FABulous_API(mocker.MagicMock())
        api.fabric = _fabric_with_real_ports()

        dumped: list[str] = []

        def _dump_and_stop(flow: FABulousFabricOptimisationFlow) -> MagicMock:
            dumped.append(flow.config.dumps())
            return mocker.MagicMock()

        mocker.patch.object(
            FABulousFabricOptimisationFlow,
            "start",
            autospec=True,
            side_effect=_dump_and_stop,
        )

        api.full_fabric_automation(
            tmp_path,
            tmp_path / "macro",
            mock_pdk_root["pdk"],
            mock_pdk_root["pdk_root"],
        )

        assert json.loads(dumped[0])
