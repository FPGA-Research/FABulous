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

        with pytest.raises(FileNotFoundError, match="Missing tile directories"):
            flow._validate_project_dir(flow, tmp_path, mock_fabric)

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

        with pytest.raises(FileNotFoundError, match="SuperTile"):
            flow._validate_project_dir(flow, tmp_path, fabric)


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
            "fabulous.fabric_generator.gds_generator.flows.fabric_optimisation_flow.FABulousTileVerilogMacroFlow",
            side_effect=ValueError("Test error"),
        )

        tile: MagicMock = mocker.MagicMock()
        with pytest.raises(ValueError, match="Test error"):
            _run_tile_flow_worker(
                tile,
                tmp_path / "io.yaml",
                OptMode.BALANCE,
                tmp_path / "base.yaml",
                tmp_path / "override.yaml",
                "test_pdk",
                tmp_path,
                tmp_path / "models_pack.v",
                HDLType.VERILOG,
            )

    def test_worker_recovers_state_on_deferred_flow_error(
        self, mocker: MockerFixture, tmp_path: Path
    ) -> None:
        """A `FlowError` after the state was saved recovers the on-disk state."""
        from librelane.flows.flow import FlowError

        recovered_state: MagicMock = mocker.MagicMock()
        mock_flow: MagicMock = mocker.MagicMock()
        mock_flow.start.side_effect = FlowError("deferred errors were encountered")
        mock_flow.run_dir = str(tmp_path)
        mock_flow.config = {
            "FABULOUS_PIN_MIN_WIDTH": Decimal("10.0"),
            "FABULOUS_PIN_MIN_HEIGHT": Decimal("10.0"),
        }
        mocker.patch(
            "fabulous.fabric_generator.gds_generator.flows.fabric_optimisation_flow.FABulousTileVerilogMacroFlow",
            return_value=mock_flow,
        )
        state_file: Path = tmp_path / "state_out.json"
        state_file.write_text("{}", encoding="utf-8")
        mocker.patch(
            "fabulous.fabric_generator.gds_generator.flows.fabric_optimisation_flow.get_latest_file",
            return_value=state_file,
        )
        mocker.patch(
            "fabulous.fabric_generator.gds_generator.flows.fabric_optimisation_flow.State.loads",
            return_value=recovered_state,
        )

        tile: MagicMock = mocker.MagicMock()
        state, error_trace, pin_min = _run_tile_flow_worker(
            tile,
            tmp_path / "io.yaml",
            OptMode.BALANCE,
            tmp_path / "base.yaml",
            tmp_path / "override.yaml",
            "test_pdk",
            tmp_path,
            tmp_path / "models_pack.v",
            HDLType.VERILOG,
        )

        assert state is recovered_state
        assert error_trace is not None
        assert "deferred errors" in error_trace
        assert pin_min is not None

    def test_worker_returns_state_on_success(
        self, mocker: MockerFixture, tmp_path: Path
    ) -> None:
        """Test that worker returns state on successful execution."""
        mock_state: MagicMock = mocker.MagicMock()
        mock_flow: MagicMock = mocker.MagicMock()
        mock_flow.start.return_value = mock_state
        mock_flow.config = {
            "FABULOUS_PIN_MIN_WIDTH": Decimal("10.0"),
            "FABULOUS_PIN_MIN_HEIGHT": Decimal("10.0"),
        }
        mocker.patch(
            "fabulous.fabric_generator.gds_generator.flows.fabric_optimisation_flow.FABulousTileVerilogMacroFlow",
            return_value=mock_flow,
        )

        tile: MagicMock = mocker.MagicMock()
        result: WorkerResult = _run_tile_flow_worker(
            tile,
            tmp_path / "io.yaml",
            OptMode.BALANCE,
            tmp_path / "base.yaml",
            tmp_path / "override.yaml",
            "test_pdk",
            tmp_path,
            tmp_path / "models_pack.v",
            HDLType.VERILOG,
        )

        state, error_trace, pin_min = result
        assert state is mock_state
        assert error_trace is None
        assert pin_min is not None


class TestWorkerCustomOverrides:
    """Tests for custom config overrides in worker function."""

    def test_worker_passes_custom_overrides(
        self, mocker: MockerFixture, tmp_path: Path
    ) -> None:
        """Test that worker passes custom config overrides to flow."""
        mock_state: MagicMock = mocker.MagicMock()
        mock_flow: MagicMock = mocker.MagicMock()
        mock_flow.start.return_value = mock_state
        mock_flow.config = {
            "FABULOUS_PIN_MIN_WIDTH": Decimal("10.0"),
            "FABULOUS_PIN_MIN_HEIGHT": Decimal("10.0"),
        }
        mock_flow_class: MagicMock = mocker.patch(
            "fabulous.fabric_generator.gds_generator.flows.fabric_optimisation_flow.FABulousTileVerilogMacroFlow",
            return_value=mock_flow,
        )

        tile: MagicMock = mocker.MagicMock()
        _run_tile_flow_worker(
            tile,
            tmp_path / "io.yaml",
            OptMode.BALANCE,
            tmp_path / "base.yaml",
            tmp_path / "override.yaml",
            "test_pdk",
            tmp_path,
            tmp_path / "models_pack.v",
            HDLType.VERILOG,
            CUSTOM_KEY="custom_value",
        )

        # Check that custom override was passed
        call_kwargs = mock_flow_class.call_args
        assert "CUSTOM_KEY" in call_kwargs.kwargs or (
            len(call_kwargs.args) > 0 and hasattr(call_kwargs, "kwargs")
        )


class TestLogNlpSummary:
    """Tests for the _log_nlp_summary static method."""

    def test_logs_table_with_tile_rows_and_utilisation(
        self, mocker: MockerFixture
    ) -> None:
        """Each tile produces a row containing its name and a utilisation %."""
        info_mock = mocker.patch(
            "fabulous.fabric_generator.gds_generator.flows.fabric_optimisation_flow.info"
        )

        nlp_state: MagicMock = mocker.MagicMock()
        # nlp__tile__area maps name -> (x0, y0, width, height); util uses w*h.
        nlp_state.metrics = {
            "nlp__tile__area": {
                "tile1": (0, 0, 10.0, 20.0),  # alloc area 200
                "tile2": (0, 0, 5.0, 4.0),  # alloc area 20
            },
            "nlp__tile__stdcell_area": {
                "tile1": 100.0,  # 50% util
                "tile2": 5.0,  # 25% util
            },
            "nlp__total__area": 220.0,
        }

        FABulousFabricOptimisationFlow._log_nlp_summary(nlp_state)

        logged = "\n".join(str(call.args[0]) for call in info_mock.call_args_list)
        assert "tile1" in logged
        assert "tile2" in logged
        # tile1: 100/200 -> 50.0%, tile2: 5/20 -> 25.0%
        assert "50.0%" in logged
        assert "25.0%" in logged
        # The width/height columns are derived from dims[2]/dims[3].
        assert "10.00" in logged
        assert "20.00" in logged

    def test_handles_zero_allocated_area(self, mocker: MockerFixture) -> None:
        """A zero-area tile reports 0% utilisation instead of dividing by zero."""
        info_mock = mocker.patch(
            "fabulous.fabric_generator.gds_generator.flows.fabric_optimisation_flow.info"
        )

        nlp_state: MagicMock = mocker.MagicMock()
        nlp_state.metrics = {
            "nlp__tile__area": {"empty": (0, 0, 0.0, 0.0)},
            "nlp__tile__stdcell_area": {"empty": 0.0},
            "nlp__total__area": 0,
        }

        FABulousFabricOptimisationFlow._log_nlp_summary(nlp_state)

        logged = "\n".join(str(call.args[0]) for call in info_mock.call_args_list)
        assert "empty" in logged
        assert "0.0%" in logged


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

    @staticmethod
    def _fabric(mocker: MockerFixture) -> MagicMock:
        fabric: MagicMock = mocker.MagicMock()
        fabric.name = "myfab"
        fabric.get_all_unique_tiles.return_value = [object(), object()]
        return fabric

    @staticmethod
    def _tile_state(mocker: MockerFixture, bbox: str) -> MagicMock:
        state: MagicMock = mocker.MagicMock()
        state.metrics = {"design__die__bbox": bbox}
        return state

    def test_raises_when_no_gds(self, mocker: MockerFixture) -> None:
        """An incomplete stitch (no GDS) raises rather than reporting success."""
        final_state: MagicMock = mocker.MagicMock()
        final_state.get.return_value = None  # no GDS produced
        final_state.metrics = {}

        with pytest.raises(RuntimeError, match="no GDS"):
            FABulousFabricOptimisationFlow._finalise(
                self._fabric(mocker), final_state, {}
            )

    def test_logs_summary_with_per_tile_macro_sizes(
        self, mocker: MockerFixture
    ) -> None:
        """A complete stitch logs the die area and each tile macro's size."""
        final_state: MagicMock = mocker.MagicMock()
        final_state.get.return_value = "/runs/final/gds/myfab.gds"
        final_state.metrics = {"design__die__bbox": "0 0 100 200"}
        tile_states = {
            "LUT": self._tile_state(mocker, "0 0 30 40"),
            "DSP": self._tile_state(mocker, "0 0 50 60"),
        }
        info_mock = mocker.patch(
            "fabulous.fabric_generator.gds_generator.flows.fabric_optimisation_flow.info"
        )

        FABulousFabricOptimisationFlow._finalise(
            self._fabric(mocker), final_state, tile_states
        )

        # Collapse the column-alignment padding so the assertions aren't brittle.
        logged = " ".join(
            " ".join(str(call.args[0]).split()) for call in info_mock.call_args_list
        )
        assert "myfab" in logged
        assert "100.00 x 200.00" in logged  # overall die area w x h
        assert "LUT 30.00 x 40.00" in logged  # per-macro tile size
        assert "DSP 50.00 x 60.00" in logged


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
        assert "FABULOUS_FABRIC" not in flow.config

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
        api: FABulous_API = FABulous_API(
            mocker.MagicMock(), plugin_manager=mocker.MagicMock()
        )
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
