"""Translation tests driving the plugin against the real CI asset configs.

Unlike `test_plugin_tile_flow` / `test_plugin_fabric_flow` (which prove the
adapter logic with synthetic fixtures and a mocked pipeline), these tests point
the adapters at the exact `tests/assets/librelane_plugin` tile and fabric the
retired `librelane-plugin.yml` nightly hardened. The real FABulous
generators run (CSV parse, switch-matrix / config-mem / tile Verilog emission,
fabric stitching, IO pin-order YAML); only the PDK-reading helpers and the
inherited `SequentialFlow.run` are stubbed, so no PDK install or EDA tool is
needed while still exercising the plugin's actual code path against realistic
inputs.

The asset tree is copied into `tmp_path` first because the adapters emit
generated Verilog next to their inputs -- running in place would dirty the
vendored assets.
"""

# ruff: noqa: SLF001

import json
import shutil
from decimal import Decimal
from pathlib import Path

import pytest
import yaml
from librelane.flows.flow import Flow
from pytest_mock import MockerFixture

from fabulous.fabric_generator.gds_generator.flows import plugin_tile_flow
from fabulous.fabric_generator.gds_generator.flows.plugin_fabric_flow import (
    FABulousFabric,
)
from fabulous.fabric_generator.gds_generator.flows.plugin_tile_flow import FABulousTile

ASSET_ROOT: Path = Path(__file__).resolve().parents[2] / "assets" / "librelane_plugin"
TILE_NAME = "LUT4x8_ha"
FABRIC_NAME = "synthetic_lut4x8_ha_10x10"


@pytest.fixture
def assets(tmp_path: Path) -> Path:
    """Copy the vendored plugin asset tree into an isolated workspace."""
    dst: Path = tmp_path / "librelane_plugin"
    shutil.copytree(ASSET_ROOT, dst)
    return dst


def _write_macro_dir(root: Path, name: str, width: str, height: str) -> Path:
    """Build a minimal hardened-macro output tree the fabric flow expects."""
    macro_dir: Path = root / name
    for sub in ("gds", "lef", "vh", "nl", "pnl"):
        (macro_dir / sub).mkdir(parents=True)
    (macro_dir / "gds" / f"{name}.gds").write_bytes(b"")
    (macro_dir / "lef" / f"{name}.lef").write_text("", encoding="utf-8")
    (macro_dir / "vh" / f"{name}.vh").write_text("", encoding="utf-8")
    (macro_dir / "nl" / f"{name}.nl.v").write_text("", encoding="utf-8")
    (macro_dir / "pnl" / f"{name}.pnl.v").write_text("", encoding="utf-8")
    (macro_dir / "metrics.json").write_text(
        json.dumps({"design__die__bbox": f"0 0 {width} {height}"}),
        encoding="utf-8",
    )
    return macro_dir


@pytest.mark.usefixtures("mock_config_load")
class TestTileRealAsset:
    """`FABulousTile.run()` against the real `LUT4x8_ha` tile asset."""

    def test_emits_real_rtl_and_populates_config(
        self, assets: Path, tmp_path: Path, mocker: MockerFixture
    ) -> None:
        tile_dir: Path = assets / "tiles" / "classic" / TILE_NAME

        # Stub only PDK-touching helpers and the real pipeline.
        mocker.patch.object(
            plugin_tile_flow, "get_pitch", return_value=(Decimal(1), Decimal(1))
        )
        mocker.patch.object(
            plugin_tile_flow, "get_routing_obstructions", return_value=[]
        )
        mocker.patch.object(plugin_tile_flow, "round_die_area", side_effect=lambda c: c)
        mocker.patch(
            "fabulous.fabric_generator.gds_generator.flows.plugin_tile_flow.SequentialFlow.run",
            return_value=(mocker.MagicMock(), []),
        )

        flow = FABulousTile(
            config={
                "DESIGN_NAME": TILE_NAME,
                "FABULOUS_TILE_DIR": [str(tile_dir)],
                # models_pack.v is not vendored; the adapter path we exercise
                # does not need it.
                "VERILOG_FILES": [],
                # Skip the DIE_AREA >= min-area comparison; this test targets
                # translation, not floorplanning math.
                "FABULOUS_IGNORE_DEFAULT_DIE_AREA": True,
                "DESIGN_DIR": str(tile_dir),
            },
            design_dir=str(tile_dir),
            pdk="sky130A",
            pdk_root=str(tmp_path / "pdk"),
        )
        flow.run_dir = str(tmp_path / "run")
        Path(flow.run_dir).mkdir()

        flow.run(initial_state=mocker.MagicMock())

        # Real per-tile RTL was emitted, including the config-mem Verilog whose
        # generator every unit test mocks out.
        assert (tile_dir / f"{TILE_NAME}.v").exists()
        assert (tile_dir / f"{TILE_NAME}_switch_matrix.v").exists()
        assert (tile_dir / f"{TILE_NAME}_ConfigMem.v").exists()
        # The .list switch matrix is read directly into the model, so no
        # bootstrap-CSV round trip is emitted.
        # IO pin-order YAML produced in the run directory.
        pin_yaml = Path(flow.run_dir) / f"{TILE_NAME}_io_pin_order.yaml"
        assert pin_yaml.exists()

        # Downstream-facing config keys are populated.
        assert flow.config["DESIGN_NAME"] == TILE_NAME
        assert flow.config["FABULOUS_IO_PIN_ORDER_CFG"] == str(pin_yaml)
        assert flow.config["FABULOUS_TILE_LOGICAL_WIDTH"] == 1
        assert flow.config["FABULOUS_TILE_LOGICAL_HEIGHT"] == 1
        verilog_files = [str(p) for p in flow.config["VERILOG_FILES"]]
        assert any(f"{TILE_NAME}.v" in p for p in verilog_files)
        assert any(f"{TILE_NAME}_switch_matrix.v" in p for p in verilog_files)


@pytest.mark.usefixtures("mock_config_load")
class TestFabricRealAsset:
    """`FABulousFabric.__init__` against the real synthetic fabric asset."""

    def test_builds_fabric_macros_and_verilog(
        self, assets: Path, tmp_path: Path
    ) -> None:
        fabric_dir: Path = assets / "fabrics" / FABRIC_NAME
        fabric_csv: Path = fabric_dir / f"{FABRIC_NAME}.csv"
        macro_dir: Path = _write_macro_dir(tmp_path / "macros", TILE_NAME, "100", "100")

        flow = FABulousFabric(
            config={
                "DESIGN_NAME": FABRIC_NAME,
                "FABULOUS_FABRIC_CONFIG": [str(fabric_csv)],
                "FABULOUS_TILE_LIBRARY": [str(assets / "tiles" / "classic")],
                "FABULOUS_TILE_MACROS": {TILE_NAME: str(macro_dir)},
                "DESIGN_DIR": str(fabric_dir),
            },
            design_dir=str(fabric_dir),
            pdk="sky130A",
            pdk_root=str(tmp_path / "pdk"),
        )

        # Real fabric parse + stitch ran and produced the fabric Verilog.
        assert (fabric_dir / "fabric.v").exists()
        # The adapter renamed the fabric to the requested design name and built
        # the macro from the hardened-output tree.
        assert flow.fabric.name == FABRIC_NAME
        assert set(flow.macros) == {TILE_NAME}
        assert flow.tile_sizes[TILE_NAME] == (Decimal(100), Decimal(100))
        assert flow.config["DESIGN_NAME"] == FABRIC_NAME
        # VERILOG_FILES was populated by the fabric-Verilog collector.
        verilog_files = [str(p) for p in flow.config["VERILOG_FILES"]]
        assert any(
            p.endswith("fabric.v") or f"{FABRIC_NAME}.v" in p for p in verilog_files
        )


class TestAssetConfigSchema:
    """The vendored `config.yaml` files still match the plugin schema.

    Catches drift between the CI asset configs and the flow classes without
    running any EDA: a `FABULOUS_*` key renamed on the flow, or a
    `meta.flow` pointing at a flow that no longer registers, would break a
    real `librelane` run at `Config.load` time.
    """

    @pytest.mark.parametrize(
        ("config_rel_path", "flow_name"),
        [
            (f"tiles/classic/{TILE_NAME}/config.yaml", "FABulousTile"),
            (f"fabrics/{FABRIC_NAME}/config.yaml", "FABulousFabric"),
        ],
    )
    def test_meta_flow_registered_and_fabulous_keys_declared(
        self, config_rel_path: str, flow_name: str
    ) -> None:
        config: dict = yaml.safe_load((ASSET_ROOT / config_rel_path).read_text())

        assert config["meta"]["flow"] == flow_name
        flow_cls = Flow.factory.get(flow_name)
        assert flow_cls is not None, f"{flow_name} is not registered"

        declared: set[str] = {v.name for v in flow_cls.config_vars}
        used_fabulous_keys: set[str] = {k for k in config if k.startswith("FABULOUS_")}
        undeclared: set[str] = used_fabulous_keys - declared
        assert not undeclared, (
            f"{config_rel_path} uses FABULOUS_* keys not declared on "
            f"{flow_name}: {undeclared}"
        )
