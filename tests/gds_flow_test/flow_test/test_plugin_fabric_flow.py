"""Tests for the `FABulousFabric` LibreLane-plugin adapter.

These tests verify the *adapting* layer: how `FABulousFabric`'s overridden
`__init__` turns plugin-level config (a fabric CSV path + a mapping of tile
name -> pre-hardened macro directory) into the `self.fabric` / `self.macros`
/ `self.tile_sizes` fields that the underlying
:class:`FABulousFabricMacroFlow` expects.
"""

# ruff: noqa: SLF001

import json
import os
from decimal import Decimal
from pathlib import Path

import pytest
from librelane.flows.flow import Flow, FlowException
from pytest_mock import MockerFixture

from fabulous.fabric_generator.gds_generator.flows import plugin_fabric_flow
from fabulous.fabric_generator.gds_generator.flows.fabric_macro_flow import (
    FABulousFabricMacroFlow,
)
from fabulous.fabric_generator.gds_generator.flows.plugin_fabric_flow import (
    FABulousFabric,
    _build_macros,
    _collect_fabric_verilog,
    _discover_tile_macros,
)


def _write_run_final(root: Path, tile: str, run: str, *, with_metrics: bool) -> Path:
    """Create `<root>/<tile>/runs/<run>/final`, optionally with metrics.json."""
    final: Path = root / tile / "runs" / run / "final"
    final.mkdir(parents=True)
    if with_metrics:
        (final / "metrics.json").write_text("{}", encoding="utf-8")
    return final


def _write_macro_dir(
    root: Path, name: str, width: str = "100", height: str = "100"
) -> Path:
    """Build a minimal macro-output tree as the fabric flow expects."""
    macro_dir: Path = root / name
    (macro_dir / "gds").mkdir(parents=True)
    (macro_dir / "lef").mkdir(parents=True)
    (macro_dir / "vh").mkdir(parents=True)
    (macro_dir / "nl").mkdir(parents=True)
    (macro_dir / "pnl").mkdir(parents=True)
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


class TestFABulousFabricSchema:
    """Schema-level assertions for the plugin wrapper."""

    def test_registered_in_flow_factory(self) -> None:
        assert Flow.factory.get("FABulousFabric") is FABulousFabric

    def test_exposes_plugin_config_vars(self) -> None:
        names: set[str] = {v.name for v in FABulousFabric.config_vars}
        assert {
            "FABULOUS_FABRIC_CONFIG",
            "FABULOUS_TILE_LIBRARY",
            "FABULOUS_TILE_MACROS",
        } <= names

    def test_inherits_underlying_config_vars(self) -> None:
        plugin_names: set[str] = {v.name for v in FABulousFabric.config_vars}
        underlying_names: set[str] = {
            v.name for v in FABulousFabricMacroFlow.config_vars
        }
        assert underlying_names <= plugin_names

    def test_subclass_of_underlying_flow(self) -> None:
        """Wrapper inherits `run()` / step substitutions from the real flow."""
        assert issubclass(FABulousFabric, FABulousFabricMacroFlow)

    def test_fabulous_fabric_config_accepts_dir_resolver_list(
        self, tmp_path: Path
    ) -> None:
        """`FABULOUS_FABRIC_CONFIG` must validate when set to `dir::...`.

        LibreLane rewrites `dir::file.csv` to `refg::$DESIGN_DIR/file.csv`
        and the refg resolver always produces a `list[str]` (see
        `librelane/config/preprocessor.py`). If the Variable is typed as a
        scalar `Path` the type validator crashes with
        `TypeError: argument should be ... not 'list'` before `run()` ever
        executes, making `dir::` unusable for this variable.
        """
        from librelane.common import GenericDict

        var = next(
            v for v in FABulousFabric.config_vars if v.name == "FABULOUS_FABRIC_CONFIG"
        )
        fabric_csv = tmp_path / "fabric.csv"
        fabric_csv.write_text("", encoding="utf-8")
        resolved_list: list[str] = [str(fabric_csv)]
        mutable = GenericDict({"FABULOUS_FABRIC_CONFIG": resolved_list})
        _, value = var.compile(mutable, warning_list_ref=[])

        # Concrete fabric path must be recoverable from whatever type we accept.
        fabric_path = Path(value[0]) if isinstance(value, list) else Path(value)
        assert fabric_path == fabric_csv


class TestBuildMacros:
    """`_build_macros` turns a tile-name -> macro-dir mapping into Macros."""

    def test_builds_macro_from_complete_directory_tree(self, tmp_path: Path) -> None:
        macro_dir: Path = _write_macro_dir(tmp_path, "LUT4AB", "150", "200")

        macros, tile_sizes = _build_macros({"LUT4AB": macro_dir})

        assert set(macros) == {"LUT4AB"}
        macro = macros["LUT4AB"]
        assert [p.name for p in macro.gds] == ["LUT4AB.gds"]
        assert macro.lef == [str(macro_dir / "lef" / "LUT4AB.lef")]
        assert macro.vh == [str(macro_dir / "vh" / "LUT4AB.vh")]
        assert macro.nl == [str(macro_dir / "nl" / "LUT4AB.nl.v")]
        assert macro.pnl == [str(macro_dir / "pnl" / "LUT4AB.pnl.v")]
        assert macro.spef == {}
        # Size comes from metrics.json "design__die__bbox"
        assert tile_sizes["LUT4AB"] == (Decimal(150), Decimal(200))

    def test_reads_width_height_from_metrics_bbox(self, tmp_path: Path) -> None:
        """Bbox is `x1 y1 x2 y2`; we take the last two as width/height."""
        macro_dir: Path = _write_macro_dir(tmp_path, "T", "42.5", "17.125")

        _, tile_sizes = _build_macros({"T": macro_dir})

        assert tile_sizes["T"] == (Decimal("42.5"), Decimal("17.125"))

    def test_collects_spef_per_corner(self, tmp_path: Path) -> None:
        macro_dir: Path = _write_macro_dir(tmp_path, "LUT4AB")
        spef_root: Path = macro_dir / "spef"
        (spef_root / "nom_tt_025C_1v80").mkdir(parents=True)
        (spef_root / "min_ff_n40C_1v95").mkdir(parents=True)
        nom_file = spef_root / "nom_tt_025C_1v80" / "LUT4AB.spef"
        min_file = spef_root / "min_ff_n40C_1v95" / "LUT4AB.spef"
        nom_file.write_text("", encoding="utf-8")
        min_file.write_text("", encoding="utf-8")

        macros, _ = _build_macros({"LUT4AB": macro_dir})

        assert set(macros["LUT4AB"].spef) == {"nom_tt_025C_1v80", "min_ff_n40C_1v95"}
        assert macros["LUT4AB"].spef["nom_tt_025C_1v80"] == [nom_file]
        assert macros["LUT4AB"].spef["min_ff_n40C_1v95"] == [min_file]

    def test_missing_spef_dir_yields_empty_spef(self, tmp_path: Path) -> None:
        macro_dir: Path = _write_macro_dir(tmp_path, "LUT4AB")

        macros, _ = _build_macros({"LUT4AB": macro_dir})

        assert macros["LUT4AB"].spef == {}

    def test_raises_when_metrics_json_missing(self, tmp_path: Path) -> None:
        macro_dir: Path = _write_macro_dir(tmp_path, "LUT4AB")
        (macro_dir / "metrics.json").unlink()

        with pytest.raises(FlowException, match="metrics.json not found"):
            _build_macros({"LUT4AB": macro_dir})

    def test_raises_when_die_bbox_missing(self, tmp_path: Path) -> None:
        macro_dir: Path = _write_macro_dir(tmp_path, "LUT4AB")
        (macro_dir / "metrics.json").write_text("{}", encoding="utf-8")

        with pytest.raises(FlowException, match="missing design__die__bbox"):
            _build_macros({"LUT4AB": macro_dir})

    def test_builds_multiple_tiles(self, tmp_path: Path) -> None:
        a = _write_macro_dir(tmp_path, "A", "100", "100")
        b = _write_macro_dir(tmp_path, "B", "200", "150")

        macros, tile_sizes = _build_macros({"A": a, "B": b})

        assert set(macros) == {"A", "B"}
        assert tile_sizes == {
            "A": (Decimal(100), Decimal(100)),
            "B": (Decimal(200), Decimal(150)),
        }


class TestCollectFabricVerilog:
    """`_collect_fabric_verilog` finds the fabric-level `*.v` files."""

    def test_finds_fabric_name_prefixed_verilog(self, tmp_path: Path) -> None:
        target: Path = tmp_path / "MyFab.v"
        target.write_text("", encoding="utf-8")

        result: list[Path] = _collect_fabric_verilog(tmp_path, "MyFab")

        assert result[0].resolve() == target.resolve()

    def test_finds_generic_fabric_v(self, tmp_path: Path) -> None:
        target: Path = tmp_path / "fabric.v"
        target.write_text("", encoding="utf-8")

        result: list[Path] = _collect_fabric_verilog(tmp_path, "MyFab")

        assert any(p.resolve() == target.resolve() for p in result)

    def test_dedupes_overlapping_candidates(self, tmp_path: Path) -> None:
        """A file matching multiple globs should appear only once."""
        # `{fabric_name}.v` is also returned by the `*.v` glob.
        (tmp_path / "MyFab.v").write_text("", encoding="utf-8")
        (tmp_path / "other.v").write_text("", encoding="utf-8")

        result: list[Path] = _collect_fabric_verilog(tmp_path, "MyFab")

        assert len(result) == len(set(result))

    def test_raises_when_no_verilog_found(self, tmp_path: Path) -> None:
        with pytest.raises(FlowException, match="No fabric Verilog found"):
            _collect_fabric_verilog(tmp_path, "MyFab")


@pytest.mark.usefixtures("mock_config_load")
class TestFABulousFabricInitAdapter:
    """Integration test for `FABulousFabric.__init__` adapter logic.

    Mocks `parseFabricCSV` so we do not depend on the CSV parser schema,
    and verifies the wrapper builds `fabric`, `macros`, `tile_sizes`
    from config variables and populates derived keys.
    """

    def test_init_builds_fabric_macros_and_sizes(
        self, mocker: MockerFixture, tmp_path: Path
    ) -> None:
        fabric_csv: Path = tmp_path / "fabric.csv"
        fabric_csv.write_text("", encoding="utf-8")
        macro_dir: Path = _write_macro_dir(tmp_path, "LUT4AB", "120", "80")
        (tmp_path / "MyFab.v").write_text("", encoding="utf-8")

        mock_fabric = mocker.MagicMock()
        mock_fabric.name = "MyFab"
        mocker.patch.object(
            plugin_fabric_flow, "parseFabricCSV", return_value=mock_fabric
        )
        mocker.patch.object(plugin_fabric_flow, "generateFabric")

        flow = FABulousFabric(
            config={
                "FABULOUS_FABRIC_CONFIG": [str(fabric_csv)],
                "FABULOUS_TILE_LIBRARY": str(tmp_path),
                "FABULOUS_TILE_MACROS": {"LUT4AB": str(macro_dir)},
                "DESIGN_DIR": str(tmp_path),
            },
            design_dir=str(tmp_path),
            pdk="sky130A",
            pdk_root=str(tmp_path / "pdk"),
        )

        assert flow.fabric is mock_fabric
        assert set(flow.macros) == {"LUT4AB"}
        assert flow.tile_sizes["LUT4AB"] == (Decimal(120), Decimal(80))
        # DESIGN_NAME defaulted from fabric.name because config omitted it.
        assert flow.config["DESIGN_NAME"] == "MyFab"
        # VERILOG_FILES was populated by the fabric-Verilog collector.
        assert any(str(p).endswith("MyFab.v") for p in flow.config["VERILOG_FILES"])

    def test_init_respects_user_supplied_design_name(
        self, mocker: MockerFixture, tmp_path: Path
    ) -> None:
        fabric_csv: Path = tmp_path / "fabric.csv"
        fabric_csv.write_text("", encoding="utf-8")
        macro_dir: Path = _write_macro_dir(tmp_path, "LUT4AB")
        (tmp_path / "MyFab.v").write_text("", encoding="utf-8")

        mock_fabric = mocker.MagicMock()
        mock_fabric.name = "MyFab"
        mocker.patch.object(
            plugin_fabric_flow, "parseFabricCSV", return_value=mock_fabric
        )
        mocker.patch.object(plugin_fabric_flow, "generateFabric")

        flow = FABulousFabric(
            config={
                "DESIGN_NAME": "CustomName",
                "FABULOUS_FABRIC_CONFIG": [str(fabric_csv)],
                "FABULOUS_TILE_LIBRARY": str(tmp_path),
                "FABULOUS_TILE_MACROS": {"LUT4AB": str(macro_dir)},
                "DESIGN_DIR": str(tmp_path),
            },
            design_dir=str(tmp_path),
            pdk="sky130A",
            pdk_root=str(tmp_path / "pdk"),
        )

        assert flow.config["DESIGN_NAME"] == "CustomName"

    def test_init_raises_on_missing_fabric_csv(
        self, mocker: MockerFixture, tmp_path: Path
    ) -> None:
        macro_dir: Path = _write_macro_dir(tmp_path, "LUT4AB")
        mocker.patch.object(plugin_fabric_flow, "parseFabricCSV")

        with pytest.raises(FlowException, match="does not exist"):
            FABulousFabric(
                config={
                    "FABULOUS_FABRIC_CONFIG": [str(tmp_path / "missing.csv")],
                    "FABULOUS_TILE_LIBRARY": str(tmp_path),
                    "FABULOUS_TILE_MACROS": {"LUT4AB": str(macro_dir)},
                    "DESIGN_DIR": str(tmp_path),
                },
                design_dir=str(tmp_path),
                pdk="sky130A",
                pdk_root=str(tmp_path / "pdk"),
            )

    def test_init_raises_on_empty_tile_macros(
        self, mocker: MockerFixture, tmp_path: Path
    ) -> None:
        fabric_csv: Path = tmp_path / "fabric.csv"
        fabric_csv.write_text("", encoding="utf-8")

        mock_fabric = mocker.MagicMock()
        mock_fabric.name = "MyFab"
        mocker.patch.object(
            plugin_fabric_flow, "parseFabricCSV", return_value=mock_fabric
        )
        mocker.patch.object(plugin_fabric_flow, "generateFabric")

        with pytest.raises(FlowException, match="FABULOUS_TILE_MACROS is empty"):
            FABulousFabric(
                config={
                    "FABULOUS_FABRIC_CONFIG": [str(fabric_csv)],
                    "FABULOUS_TILE_LIBRARY": str(tmp_path),
                    "FABULOUS_TILE_MACROS": {},
                    "DESIGN_DIR": str(tmp_path),
                },
                design_dir=str(tmp_path),
                pdk="sky130A",
                pdk_root=str(tmp_path / "pdk"),
            )


class TestDiscoverTileMacros:
    """`_discover_tile_macros` resolves hardened tile run directories."""

    def test_picks_newest_run_with_metrics(self, tmp_path: Path) -> None:
        old: Path = _write_run_final(tmp_path, "LUT4AB", "RUN_OLD", with_metrics=True)
        new: Path = _write_run_final(tmp_path, "LUT4AB", "RUN_NEW", with_metrics=True)
        os.utime(old, (1000, 1000))
        os.utime(new, (2000, 2000))

        assert _discover_tile_macros(["LUT4AB"], [tmp_path]) == {"LUT4AB": new}

    def test_skips_run_without_metrics_even_if_newer(self, tmp_path: Path) -> None:
        good: Path = _write_run_final(tmp_path, "LUT4AB", "RUN_OLD", with_metrics=True)
        newer_bad: Path = _write_run_final(
            tmp_path, "LUT4AB", "RUN_NEW", with_metrics=False
        )
        os.utime(good, (1000, 1000))
        os.utime(newer_bad, (2000, 2000))

        # The newer run has no metrics.json, so it is not a usable macro.
        assert _discover_tile_macros(["LUT4AB"], [tmp_path]) == {"LUT4AB": good}

    def test_omits_tile_with_no_valid_run(self, tmp_path: Path) -> None:
        _write_run_final(tmp_path, "LUT4AB", "RUN_NEW", with_metrics=False)

        assert _discover_tile_macros(["LUT4AB", "MISSING"], [tmp_path]) == {}


@pytest.mark.usefixtures("mock_config_load")
class TestAutoDiscoveryIncludesSuperTiles:
    """Auto-discovery must resolve super-tile macros, not just standalone tiles."""

    def test_supertile_names_passed_to_discovery(
        self, mocker: MockerFixture, tmp_path: Path
    ) -> None:
        fabric_csv: Path = tmp_path / "fabric.csv"
        fabric_csv.write_text("", encoding="utf-8")
        (tmp_path / "MyFab.v").write_text("", encoding="utf-8")

        regular = mocker.MagicMock()
        regular.name = "LUT4AB"
        regular.partOfSuperTile = False
        subtile = mocker.MagicMock()
        subtile.name = "DSP_top"
        subtile.partOfSuperTile = True

        mock_fabric = mocker.MagicMock()
        mock_fabric.name = "MyFab"
        mock_fabric.tileDic = {"LUT4AB": regular, "DSP_top": subtile}
        mock_fabric.superTileDic = {"DSP": mocker.MagicMock()}

        mocker.patch.object(
            plugin_fabric_flow, "parseFabricCSV", return_value=mock_fabric
        )
        mocker.patch.object(plugin_fabric_flow, "generateFabric")
        discover = mocker.patch.object(
            plugin_fabric_flow,
            "_discover_tile_macros",
            return_value={"LUT4AB": tmp_path, "DSP": tmp_path},
        )
        mocker.patch.object(plugin_fabric_flow, "_build_macros", return_value=({}, {}))

        FABulousFabric(
            config={
                "FABULOUS_FABRIC_CONFIG": [str(fabric_csv)],
                "FABULOUS_TILE_LIBRARY": str(tmp_path),
                "DESIGN_DIR": str(tmp_path),
            },
            design_dir=str(tmp_path),
            pdk="sky130A",
            pdk_root=str(tmp_path / "pdk"),
        )

        passed_names = discover.call_args.args[0]
        # Super-tile name resolved, standalone tile resolved, sub-tile excluded
        # (its macro is hardened under the super-tile name, not on its own).
        assert "DSP" in passed_names
        assert "LUT4AB" in passed_names
        assert "DSP_top" not in passed_names
