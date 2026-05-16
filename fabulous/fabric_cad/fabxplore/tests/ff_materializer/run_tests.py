"""Ad-hoc tests for FF materialization."""

from pathlib import Path
from tempfile import TemporaryDirectory

from fabulous.fabric_cad.fabxplore.pyosys.custom_passes.ff_materializer_pass import (
    FfMaterializerPass,
)
from fabulous.fabric_cad.fabxplore.pyosys.pyosys_bridge import PyosysBridge
from fabulous.fabulous_cli.helper import setup_logger

setup_logger(verbosity=0, debug=False)


def test_single_dff_materialization() -> None:
    """Test one scalar FF is replaced by one tile instance."""
    with TemporaryDirectory(prefix="ff_mat_single_") as td:
        tmp_dir = Path(td)
        base = _write_single_dff_base(tmp_dir)
        tile = _write_tile(tmp_dir)

        bridge = _load_base(base)
        result = _run_materializer(bridge, tile, pack=True)

        assert result.result_data is not None
        assert result.result_data.stats.materialized_ffs == 1
        assert result.result_data.stats.inserted_tiles == 1
        cells = bridge.to_netlist_dict()["modules"]["base"]["cells"]
        assert not _has_cell_type(cells, "$dff")
        tile_cells = _cells_by_type(cells, "reg_tile")
        assert len(tile_cells) == 1
        assert {"I0", "Q0", "CLK", "ConfigBits"} <= set(tile_cells[0]["connections"])
        assert tile_cells[0]["connections"]["ConfigBits"][2] == "1"
        bridge.run_pass("hierarchy -top base -check")


def test_two_ffs_pack_into_one_tile() -> None:
    """Test two independent FFs can fill two lanes in one tile."""
    with TemporaryDirectory(prefix="ff_mat_pack_") as td:
        tmp_dir = Path(td)
        base = _write_two_dff_base(tmp_dir)
        tile = _write_tile(tmp_dir)

        bridge = _load_base(base)
        result = _run_materializer(bridge, tile, pack=True)

        assert result.result_data is not None
        assert result.result_data.stats.materialized_ffs == 2
        assert result.result_data.stats.inserted_tiles == 1
        cells = bridge.to_netlist_dict()["modules"]["base"]["cells"]
        assert len(_cells_by_type(cells, "reg_tile")) == 1
        assert not _has_cell_type(cells, "$dff")


def test_pack_disabled_creates_one_tile_per_ff() -> None:
    """Test disabling packing creates one replacement tile for each FF."""
    with TemporaryDirectory(prefix="ff_mat_no_pack_") as td:
        tmp_dir = Path(td)
        base = _write_two_dff_base(tmp_dir)
        tile = _write_tile(tmp_dir)

        bridge = _load_base(base)
        result = _run_materializer(bridge, tile, pack=False)

        assert result.result_data is not None
        assert result.result_data.stats.materialized_ffs == 2
        assert result.result_data.stats.inserted_tiles == 2
        cells = bridge.to_netlist_dict()["modules"]["base"]["cells"]
        assert len(_cells_by_type(cells, "reg_tile")) == 2


def test_ff_chain_is_preserved_when_packed() -> None:
    """Test a two-FF pipeline keeps the intermediate net between lanes."""
    with TemporaryDirectory(prefix="ff_mat_chain_") as td:
        tmp_dir = Path(td)
        base = _write_chain_base(tmp_dir)
        tile = _write_tile(tmp_dir)

        bridge = _load_base(base)
        _run_materializer(bridge, tile, pack=True)

        cells = bridge.to_netlist_dict()["modules"]["base"]["cells"]
        tile_cell = _cells_by_type(cells, "reg_tile")[0]
        output_nets = {
            tuple(tile_cell["connections"]["Q0"]),
            tuple(tile_cell["connections"]["Q1"]),
        }
        input_nets = {
            tuple(tile_cell["connections"]["I0"]),
            tuple(tile_cell["connections"]["I1"]),
        }
        assert output_nets & input_nets
        assert not _has_cell_type(cells, "$dff")


def test_dffe_with_variable_enable_is_skipped_by_default() -> None:
    """Test variable enable FFs are skipped unless a lane opts in."""
    with TemporaryDirectory(prefix="ff_mat_dffe_skip_") as td:
        tmp_dir = Path(td)
        base = _write_dffe_base(tmp_dir)
        tile = _write_tile(tmp_dir)

        bridge = _load_base(base)
        result = _run_materializer(bridge, tile, pack=True, include_enable=False)

        assert result.result_data is not None
        assert result.result_data.stats.materialized_ffs == 0
        assert result.result_data.stats.skipped_control_mismatch == 1
        cells = bridge.to_netlist_dict()["modules"]["base"]["cells"]
        assert _has_cell_type(cells, "$dffe")


def test_dffe_enable_can_be_wired_to_tile() -> None:
    """Test enabled FFs can wire their enable signal to a tile port."""
    with TemporaryDirectory(prefix="ff_mat_dffe_wire_") as td:
        tmp_dir = Path(td)
        base = _write_dffe_base(tmp_dir)
        tile = _write_tile(tmp_dir)

        bridge = _load_base(base)
        result = _run_materializer(bridge, tile, pack=True, include_enable=True)

        assert result.result_data is not None
        assert result.result_data.stats.materialized_ffs == 1
        cells = bridge.to_netlist_dict()["modules"]["base"]["cells"]
        tile_cell = _cells_by_type(cells, "reg_tile")[0]
        assert "EN" in tile_cell["connections"]
        assert not _has_cell_type(cells, "$dffe")


def test_sdff_reset_can_be_wired_to_tile() -> None:
    """Test reset FFs can wire their reset signal to a tile port."""
    with TemporaryDirectory(prefix="ff_mat_sdff_wire_") as td:
        tmp_dir = Path(td)
        base = _write_sdff_base(tmp_dir, reset_value=0)
        tile = _write_tile(tmp_dir)

        bridge = _load_base(base)
        result = _run_materializer(bridge, tile, pack=True, include_reset=True)

        assert result.result_data is not None
        assert result.result_data.stats.materialized_ffs == 1
        cells = bridge.to_netlist_dict()["modules"]["base"]["cells"]
        tile_cell = _cells_by_type(cells, "reg_tile")[0]
        assert "SR" in tile_cell["connections"]
        assert not _has_cell_type(cells, "$sdff")


def test_reset_value_mismatch_is_skipped() -> None:
    """Test reset value mismatch prevents materialization."""
    with TemporaryDirectory(prefix="ff_mat_reset_mismatch_") as td:
        tmp_dir = Path(td)
        base = _write_sdff_base(tmp_dir, reset_value=1)
        tile = _write_tile(tmp_dir)

        bridge = _load_base(base)
        result = _run_materializer(bridge, tile, pack=True, include_reset=True)

        assert result.result_data is not None
        assert result.result_data.stats.materialized_ffs == 0
        cells = bridge.to_netlist_dict()["modules"]["base"]["cells"]
        assert _has_cell_type(cells, "$sdff")


def test_config_conflict_prevents_packing_second_ff() -> None:
    """Test conflicting config bits start a second replacement tile."""
    with TemporaryDirectory(prefix="ff_mat_config_conflict_") as td:
        tmp_dir = Path(td)
        base = _write_two_dff_base(tmp_dir)
        tile = _write_tile(tmp_dir)

        bridge = _load_base(base)
        result = _run_materializer(
            bridge,
            tile,
            pack=True,
            second_lane_config={"ConfigBits[2]": 0},
        )

        assert result.result_data is not None
        assert result.result_data.stats.materialized_ffs == 2
        assert result.result_data.stats.inserted_tiles == 2


def test_fail_on_pack_conflict_raises() -> None:
    """Test manual config packing conflicts can be hard errors."""
    with TemporaryDirectory(prefix="ff_mat_fail_pack_conflict_") as td:
        tmp_dir = Path(td)
        base = _write_two_dff_base(tmp_dir)
        tile = _write_tile(tmp_dir)

        bridge = _load_base(base)
        error_message = ""
        try:
            _run_materializer(
                bridge,
                tile,
                pack=True,
                second_lane_config={"ConfigBits[2]": 0},
                fail_on_pack_conflict=True,
            )
        except RuntimeError as exc:
            error_message = str(exc)
        if not error_message:
            raise AssertionError("expected packing conflict to fail")
        assert "Config, parameter, or port conflict" in error_message


def test_max_replacements_limits_materialization() -> None:
    """Test max_replacements caps replaced FFs."""
    with TemporaryDirectory(prefix="ff_mat_limit_") as td:
        tmp_dir = Path(td)
        base = _write_two_dff_base(tmp_dir)
        tile = _write_tile(tmp_dir)

        bridge = _load_base(base)
        result = _run_materializer(bridge, tile, pack=True, max_replacements=1)

        assert result.result_data is not None
        assert result.result_data.stats.materialized_ffs == 1
        assert result.result_data.stats.skipped_limit == 1
        cells = bridge.to_netlist_dict()["modules"]["base"]["cells"]
        assert _has_cell_type(cells, "$dff")


def test_escaped_ff_name_materialization() -> None:
    """Test generated escaped FF names round-trip through the writer."""
    with TemporaryDirectory(prefix="ff_mat_escaped_") as td:
        tmp_dir = Path(td)
        base = _write_escaped_base(tmp_dir)
        tile = _write_tile(tmp_dir)

        bridge = _load_base(base)
        result = _run_materializer(bridge, tile, pack=True)

        assert result.result_data is not None
        assert result.result_data.stats.materialized_ffs == 1
        cells = bridge.to_netlist_dict()["modules"]["base"]["cells"]
        assert not _has_cell_type(cells, "$dff")


def test_no_auto_config_replaces_without_config_updates() -> None:
    """Test lanes without config and global auto_config just replace the FF."""
    with TemporaryDirectory(prefix="ff_mat_no_auto_cfg_") as td:
        tmp_dir = Path(td)
        base = _write_single_dff_base(tmp_dir)
        tile = _write_auto_config_tile(tmp_dir)

        bridge = _load_base(base)
        result = _run_auto_materializer(
            bridge=bridge,
            tile=tile,
            auto_config=False,
            lanes=[
                {
                    "data_port": "I0",
                    "output_port": "Q0",
                    "clock_port": "CLK",
                }
            ],
        )

        assert result.result_data is not None
        assert result.result_data.stats.materialized_ffs == 1
        cells = bridge.to_netlist_dict()["modules"]["base"]["cells"]
        tile_cell = _cells_by_type(cells, "auto_reg_tile")[0]
        assert "ConfigBits" not in tile_cell["connections"]


def test_auto_config_solves_identity_config_and_is_equivalent() -> None:
    """Test auto_config solves config bits and preserves FF behavior."""
    with TemporaryDirectory(prefix="ff_mat_auto_cfg_") as td:
        tmp_dir = Path(td)
        base = _write_single_dff_base(tmp_dir)
        tile = _write_auto_config_tile(tmp_dir)

        bridge = _load_base(base)
        result = _run_auto_materializer(
            bridge=bridge,
            tile=tile,
            auto_config=True,
            lanes=[
                {
                    "data_port": "I0",
                    "output_port": "Q0",
                    "clock_port": "CLK",
                }
            ],
        )

        assert result.result_data is not None
        assert result.result_data.stats.materialized_ffs == 1
        cells = bridge.to_netlist_dict()["modules"]["base"]["cells"]
        tile_cell = _cells_by_type(cells, "auto_reg_tile")[0]
        assert tile_cell["connections"]["ConfigBits"][0] == "1"
        _assert_equivalent(base=base, gate_bridge=bridge, tile=tile)


def test_auto_config_uses_global_overwrites_as_constraint() -> None:
    """Test global overwrites constrain auto_config and SAT fills the rest."""
    with TemporaryDirectory(prefix="ff_mat_auto_constraint_") as td:
        tmp_dir = Path(td)
        base = _write_single_dff_base(tmp_dir)
        tile = _write_auto_config_constraint_tile(tmp_dir)

        bridge = _load_base(base)
        result = _run_auto_materializer(
            bridge=bridge,
            tile=tile,
            auto_config=True,
            auto_config_overwrites={"ConfigBits[0]": 1},
            lanes=[
                {
                    "data_port": "I0",
                    "output_port": "Q0",
                    "clock_port": "CLK",
                }
            ],
        )

        assert result.result_data is not None
        report = result.result_data.report_summary
        assert "- auto_config: True" in report
        assert "  - ConfigBits[0] = 1" in report
        assert "- pack_multiple_ffs_per_tile: True" in report
        assert "- max_replacements: none" in report
        assert "- fail_on_pack_conflict: False" in report
        cells = bridge.to_netlist_dict()["modules"]["base"]["cells"]
        tile_cell = _cells_by_type(cells, "auto_constraint_tile")[0]
        assert tile_cell["connections"]["ConfigBits"][0] == "1"
        assert tile_cell["connections"]["ConfigBits"][1] == "1"
        _assert_equivalent(base=base, gate_bridge=bridge, tile=tile)


def test_auto_config_lowers_priority_mux_tile() -> None:
    """Test auto_config accepts tile BLIF containing Yosys ``$pmux`` cells."""
    with TemporaryDirectory(prefix="ff_mat_auto_pmux_") as td:
        tmp_dir = Path(td)
        base = _write_single_dff_base(tmp_dir)
        tile = _write_auto_priority_mux_tile(tmp_dir)

        bridge = _load_base(base)
        result = _run_auto_materializer(
            bridge=bridge,
            tile=tile,
            auto_config=True,
            lanes=[
                {
                    "data_port": "I0",
                    "output_port": "Q0",
                    "clock_port": "CLK",
                }
            ],
        )

        assert result.result_data is not None
        assert result.result_data.stats.materialized_ffs == 1
        _assert_equivalent(base=base, gate_bridge=bridge, tile=tile)


def test_auto_config_imports_all_candidate_inputs() -> None:
    """Test auto_config handles candidate cones using unbound tile inputs."""
    with TemporaryDirectory(prefix="ff_mat_auto_missing_input_") as td:
        tmp_dir = Path(td)
        base = _write_single_dff_base(tmp_dir)
        tile = _write_auto_config_external_input_tile(tmp_dir)

        bridge = _load_base(base)
        result = _run_auto_materializer(
            bridge=bridge,
            tile=tile,
            auto_config=True,
            lanes=[
                {
                    "data_port": "I0",
                    "output_port": "Q0",
                    "clock_port": "CLK",
                }
            ],
        )

        assert result.result_data is not None
        assert result.result_data.stats.materialized_ffs == 1
        cells = bridge.to_netlist_dict()["modules"]["base"]["cells"]
        tile_cell = _cells_by_type(cells, "auto_external_input_tile")[0]
        assert tile_cell["connections"]["ConfigBits"][0] == "1"
        _assert_equivalent(base=base, gate_bridge=bridge, tile=tile)


def test_auto_config_neutralizes_shared_register_controls() -> None:
    """Test auto_config fixes shared EN/SR controls while solving identity."""
    with TemporaryDirectory(prefix="ff_mat_auto_control_neutral_") as td:
        tmp_dir = Path(td)
        base = _write_single_dff_base(tmp_dir)
        tile = _write_auto_config_controlled_tile(tmp_dir)

        bridge = _load_base(base)
        result = _run_auto_materializer(
            bridge=bridge,
            tile=tile,
            tile_inputs=["I0", "I1", "CLK", "EN", "SR"],
            auto_config=True,
            lanes=[
                {
                    "data_port": "I0",
                    "output_port": "Q0",
                    "clock_port": "CLK",
                    "enable_tile_port": "EN",
                    "enable_neutral": 1,
                    "reset_tile_port": "SR",
                    "reset_neutral": 0,
                    "reset_kind": "sync",
                    "reset_value": 0,
                }
            ],
        )

        assert result.result_data is not None
        assert result.result_data.stats.materialized_ffs == 1
        cells = bridge.to_netlist_dict()["modules"]["base"]["cells"]
        tile_cell = _cells_by_type(cells, "auto_controlled_tile")[0]
        assert tile_cell["connections"]["EN"][0] == "1"
        assert tile_cell["connections"]["SR"][0] == "0"
        assert tile_cell["connections"]["ConfigBits"][0] == "1"
        _assert_equivalent(base=base, gate_bridge=bridge, tile=tile)


def test_auto_config_neutralizes_independent_lane_controls() -> None:
    """Test auto_config supports separate control ports for packed lanes."""
    with TemporaryDirectory(prefix="ff_mat_auto_independent_controls_") as td:
        tmp_dir = Path(td)
        base = _write_two_dff_base(tmp_dir)
        tile = _write_auto_config_independent_control_tile(tmp_dir)

        bridge = _load_base(base)
        result = _run_auto_materializer(
            bridge=bridge,
            tile=tile,
            tile_inputs=["I0", "I1", "CLK", "EN0", "SR0", "EN1", "SR1"],
            auto_config=True,
            lanes=[
                {
                    "data_port": "I0",
                    "output_port": "Q0",
                    "clock_port": "CLK",
                    "enable_tile_port": "EN0",
                    "enable_neutral": 1,
                    "reset_tile_port": "SR0",
                    "reset_neutral": 0,
                    "reset_kind": "sync",
                    "reset_value": 0,
                },
                {
                    "data_port": "I1",
                    "output_port": "Q1",
                    "clock_port": "CLK",
                    "enable_tile_port": "EN1",
                    "enable_neutral": 1,
                    "reset_tile_port": "SR1",
                    "reset_neutral": 0,
                    "reset_kind": "sync",
                    "reset_value": 0,
                },
            ],
        )

        assert result.result_data is not None
        assert result.result_data.stats.materialized_ffs == 2
        assert result.result_data.stats.inserted_tiles == 1
        cells = bridge.to_netlist_dict()["modules"]["base"]["cells"]
        tile_cell = _cells_by_type(cells, "auto_independent_control_tile")[0]
        assert tile_cell["connections"]["EN0"][0] == "1"
        assert tile_cell["connections"]["SR0"][0] == "0"
        assert tile_cell["connections"]["EN1"][0] == "1"
        assert tile_cell["connections"]["SR1"][0] == "0"
        _assert_equivalent(base=base, gate_bridge=bridge, tile=tile)


def test_shared_enable_neutral_conflict_raises() -> None:
    """Test reused enable ports must agree on neutral value."""
    with TemporaryDirectory(prefix="ff_mat_enable_conflict_") as td:
        tmp_dir = Path(td)
        base = _write_two_dff_base(tmp_dir)
        tile = _write_auto_config_controlled_tile(tmp_dir)

        bridge = _load_base(base)
        error_message = ""
        try:
            _run_auto_materializer(
                bridge=bridge,
                tile=tile,
                tile_inputs=["I0", "I1", "CLK", "EN", "SR"],
                auto_config=False,
                lanes=[
                    {
                        "data_port": "I0",
                        "output_port": "Q0",
                        "clock_port": "CLK",
                        "enable_tile_port": "EN",
                        "enable_neutral": 1,
                    },
                    {
                        "data_port": "I1",
                        "output_port": "Q1",
                        "clock_port": "CLK",
                        "enable_tile_port": "EN",
                        "enable_neutral": 0,
                    },
                ],
            )
        except RuntimeError as exc:
            error_message = str(exc)
        if not error_message:
            raise AssertionError("expected shared enable conflict")
        assert "reuses enable port 'EN'" in error_message


def test_shared_reset_setting_conflict_raises() -> None:
    """Test reused reset ports must agree on reset settings."""
    with TemporaryDirectory(prefix="ff_mat_reset_conflict_") as td:
        tmp_dir = Path(td)
        base = _write_two_dff_base(tmp_dir)
        tile = _write_auto_config_controlled_tile(tmp_dir)

        bridge = _load_base(base)
        error_message = ""
        try:
            _run_auto_materializer(
                bridge=bridge,
                tile=tile,
                tile_inputs=["I0", "I1", "CLK", "EN", "SR"],
                auto_config=False,
                lanes=[
                    {
                        "data_port": "I0",
                        "output_port": "Q0",
                        "clock_port": "CLK",
                        "reset_tile_port": "SR",
                        "reset_neutral": 0,
                        "reset_kind": "sync",
                        "reset_value": 0,
                    },
                    {
                        "data_port": "I1",
                        "output_port": "Q1",
                        "clock_port": "CLK",
                        "reset_tile_port": "SR",
                        "reset_neutral": 0,
                        "reset_kind": "sync",
                        "reset_value": 1,
                    },
                ],
            )
        except RuntimeError as exc:
            error_message = str(exc)
        if not error_message:
            raise AssertionError("expected shared reset conflict")
        assert "reuses reset port 'SR'" in error_message


def test_auto_config_unsat_constraint_raises() -> None:
    """Test an impossible auto_config constraint fails clearly.

    Raises
    ------
    AssertionError
        If the impossible lane is accepted.
    """
    with TemporaryDirectory(prefix="ff_mat_auto_unsat_") as td:
        tmp_dir = Path(td)
        base = _write_single_dff_base(tmp_dir)
        tile = _write_auto_config_tile(tmp_dir)

        bridge = _load_base(base)
        error_message = ""
        try:
            _run_auto_materializer(
                bridge=bridge,
                tile=tile,
                auto_config=True,
                auto_config_overwrites={"ConfigBits[0]": 0},
                lanes=[
                    {
                        "data_port": "I0",
                        "output_port": "Q0",
                        "clock_port": "CLK",
                    }
                ],
                fail_on_auto_config_unsat=True,
            )
        except RuntimeError as exc:
            error_message = str(exc)
        if not error_message:
            raise AssertionError("expected unsat auto_config lane to fail")
        assert "auto_config cannot implement" in error_message


def test_auto_config_conflict_prevents_packing_second_ff() -> None:
    """Test auto-solved config conflicts create a second tile."""
    with TemporaryDirectory(prefix="ff_mat_auto_pack_conflict_") as td:
        tmp_dir = Path(td)
        base = _write_two_dff_base(tmp_dir)
        tile = _write_auto_pack_conflict_tile(tmp_dir)

        bridge = _load_base(base)
        result = _run_auto_materializer(
            bridge=bridge,
            tile=tile,
            auto_config=True,
            lanes=[
                {
                    "data_port": "I0",
                    "output_port": "Q0",
                    "clock_port": "CLK",
                },
                {
                    "data_port": "I1",
                    "output_port": "Q1",
                    "clock_port": "CLK",
                },
            ],
        )

        assert result.result_data is not None
        assert result.result_data.stats.materialized_ffs == 2
        assert result.result_data.stats.inserted_tiles == 2


def test_auto_config_fail_on_unsat_group_raises() -> None:
    """Test auto_config raises when requested for an unsat packed lane set."""
    with TemporaryDirectory(prefix="ff_mat_auto_unsat_group_") as td:
        tmp_dir = Path(td)
        base = _write_two_dff_base(tmp_dir)
        tile = _write_auto_pack_conflict_tile(tmp_dir)

        bridge = _load_base(base)
        error_message = ""
        try:
            _run_auto_materializer(
                bridge=bridge,
                tile=tile,
                auto_config=True,
                fail_on_auto_config_unsat=True,
                lanes=[
                    {
                        "data_port": "I0",
                        "output_port": "Q0",
                        "clock_port": "CLK",
                    },
                    {
                        "data_port": "I1",
                        "output_port": "Q1",
                        "clock_port": "CLK",
                    },
                ],
            )
        except RuntimeError as exc:
            error_message = str(exc)
        if not error_message:
            raise AssertionError("expected packed auto_config to fail")
        assert "auto_config cannot implement identity for lanes" in error_message


def test_auto_config_shared_solution_packs_two_ffs() -> None:
    """Test global auto_config solves a shared two-output identity config."""
    with TemporaryDirectory(prefix="ff_mat_auto_pack_shared_") as td:
        tmp_dir = Path(td)
        base = _write_two_dff_base(tmp_dir)
        tile = _write_auto_shared_solution_tile(tmp_dir)

        bridge = _load_base(base)
        result = _run_auto_materializer(
            bridge=bridge,
            tile=tile,
            auto_config=True,
            lanes=[
                {
                    "data_port": "I0",
                    "output_port": "Q0",
                    "clock_port": "CLK",
                },
                {
                    "data_port": "I1",
                    "output_port": "Q1",
                    "clock_port": "CLK",
                },
            ],
        )

        assert result.result_data is not None
        assert result.result_data.stats.materialized_ffs == 2
        assert result.result_data.stats.inserted_tiles == 1
        cells = bridge.to_netlist_dict()["modules"]["base"]["cells"]
        tile_cell = _cells_by_type(cells, "auto_shared_solution_tile")[0]
        assert tile_cell["connections"]["ConfigBits"][0] == "1"
        _assert_equivalent(base=base, gate_bridge=bridge, tile=tile)


def test_auto_config_rejects_lane_local_config() -> None:
    """Test global auto_config rejects ambiguous lane-local config."""
    with TemporaryDirectory(prefix="ff_mat_auto_lane_config_") as td:
        tmp_dir = Path(td)
        base = _write_single_dff_base(tmp_dir)
        tile = _write_auto_config_tile(tmp_dir)

        bridge = _load_base(base)
        error_message = ""
        try:
            _run_auto_materializer(
                bridge=bridge,
                tile=tile,
                auto_config=True,
                lanes=[
                    {
                        "data_port": "I0",
                        "output_port": "Q0",
                        "clock_port": "CLK",
                        "config": {"ConfigBits[0]": 1},
                    }
                ],
            )
        except RuntimeError as exc:
            error_message = str(exc)
        if not error_message:
            raise AssertionError("expected lane-local config to fail")
        assert "config is not allowed when auto_config=True" in error_message


def test_single_sequential_input_lane_is_equivalent() -> None:
    """Test a tile lane whose input side contains the register."""
    with TemporaryDirectory(prefix="ff_mat_seq_input_one_") as td:
        tmp_dir = Path(td)
        base = _write_many_dff_base(tmp_dir, count=1)
        tile = _write_sequential_input_tile(tmp_dir, count=1)

        bridge = _load_base(base)
        result = _run_custom_materializer(
            bridge=bridge,
            tile=tile,
            tile_inputs=["I0", "CLK"],
            tile_outputs=["O0"],
            lanes=[
                {
                    "data_port": "I0",
                    "output_port": "O0",
                    "clock_port": "CLK",
                }
            ],
        )

        assert result.result_data is not None
        assert result.result_data.stats.materialized_ffs == 1
        assert result.result_data.stats.inserted_tiles == 1
        _assert_equivalent(base=base, gate_bridge=bridge, tile=tile)


def test_two_sequential_input_lanes_pack_and_are_equivalent() -> None:
    """Test two input-side register lanes can be packed together."""
    with TemporaryDirectory(prefix="ff_mat_seq_input_two_") as td:
        tmp_dir = Path(td)
        base = _write_many_dff_base(tmp_dir, count=2)
        tile = _write_sequential_input_tile(tmp_dir, count=2)

        bridge = _load_base(base)
        result = _run_custom_materializer(
            bridge=bridge,
            tile=tile,
            tile_inputs=["I0", "I1", "CLK"],
            tile_outputs=["O0", "O1"],
            lanes=[
                {
                    "data_port": "I0",
                    "output_port": "O0",
                    "clock_port": "CLK",
                },
                {
                    "data_port": "I1",
                    "output_port": "O1",
                    "clock_port": "CLK",
                },
            ],
        )

        assert result.result_data is not None
        assert result.result_data.stats.materialized_ffs == 2
        assert result.result_data.stats.inserted_tiles == 1
        _assert_equivalent(base=base, gate_bridge=bridge, tile=tile)


def test_five_sequential_input_lanes_pack_and_are_equivalent() -> None:
    """Test a wider tile where every materialized FF is input-side sequential."""
    with TemporaryDirectory(prefix="ff_mat_seq_input_five_") as td:
        tmp_dir = Path(td)
        base = _write_many_dff_base(tmp_dir, count=5)
        tile = _write_sequential_input_tile(tmp_dir, count=5)

        bridge = _load_base(base)
        result = _run_custom_materializer(
            bridge=bridge,
            tile=tile,
            tile_inputs=["I0", "I1", "I2", "I3", "I4", "CLK"],
            tile_outputs=["O0", "O1", "O2", "O3", "O4"],
            lanes=[
                {
                    "data_port": f"I{index}",
                    "output_port": f"O{index}",
                    "clock_port": "CLK",
                }
                for index in range(5)
            ],
        )

        assert result.result_data is not None
        assert result.result_data.stats.materialized_ffs == 5
        assert result.result_data.stats.inserted_tiles == 1
        _assert_equivalent(base=base, gate_bridge=bridge, tile=tile)


def test_mixed_sequential_input_and_output_lanes_are_equivalent() -> None:
    """Test one tile mixing input-side and output-side register lanes."""
    with TemporaryDirectory(prefix="ff_mat_seq_mixed_five_") as td:
        tmp_dir = Path(td)
        base = _write_many_dff_base(tmp_dir, count=5)
        tile = _write_mixed_sequential_tile(tmp_dir)

        bridge = _load_base(base)
        result = _run_custom_materializer(
            bridge=bridge,
            tile=tile,
            tile_inputs=["I0", "I1", "I2", "I3", "I4", "CLK"],
            tile_outputs=["O0", "Q1", "O2", "Q3", "Q4"],
            lanes=[
                {
                    "data_port": "I0",
                    "output_port": "O0",
                    "clock_port": "CLK",
                },
                {
                    "data_port": "I1",
                    "output_port": "Q1",
                    "clock_port": "CLK",
                },
                {
                    "data_port": "I2",
                    "output_port": "O2",
                    "clock_port": "CLK",
                },
                {
                    "data_port": "I3",
                    "output_port": "Q3",
                    "clock_port": "CLK",
                },
                {
                    "data_port": "I4",
                    "output_port": "Q4",
                    "clock_port": "CLK",
                },
            ],
        )

        assert result.result_data is not None
        assert result.result_data.stats.materialized_ffs == 5
        assert result.result_data.stats.inserted_tiles == 1
        _assert_equivalent(base=base, gate_bridge=bridge, tile=tile)


def test_manual_depth_two_lane_replaces_two_ff_chain() -> None:
    """Test a depth-two lane consumes two chained FFs and preserves latency."""
    with TemporaryDirectory(prefix="ff_mat_depth_two_") as td:
        tmp_dir = Path(td)
        base = _write_pipeline_base(tmp_dir, depth=2)
        tile = _write_configurable_depth_tile(tmp_dir)

        bridge = _load_base(base)
        result = _run_custom_materializer(
            bridge=bridge,
            tile=tile,
            tile_inputs=["I0", "CLK"],
            tile_outputs=["Q0"],
            lanes=[
                {
                    "data_port": "I0",
                    "output_port": "Q0",
                    "clock_port": "CLK",
                    "depth_options": [
                        {
                            "depth": 2,
                            "mode_config": {
                                "ConfigBits[0]": 1,
                                "ConfigBits[1]": 0,
                            },
                        }
                    ],
                }
            ],
            tile_config_prefixes=["ConfigBits"],
        )

        assert result.result_data is not None
        assert result.result_data.stats.materialized_ffs == 2
        assert result.result_data.stats.inserted_tiles == 1
        assert "depth 2: 1" in result.result_data.report_summary
        cells = bridge.to_netlist_dict()["modules"]["base"]["cells"]
        assert not _has_cell_type(cells, "$dff")
        _assert_equivalent(base=base, gate_bridge=bridge, tile=tile, seq_depth=4)


def test_manual_configurable_depth_chunks_long_chain() -> None:
    """Test a long chain is split into legal depth chunks."""
    with TemporaryDirectory(prefix="ff_mat_depth_chunks_") as td:
        tmp_dir = Path(td)
        base = _write_pipeline_base(tmp_dir, depth=5)
        tile = _write_configurable_depth_tile(tmp_dir)

        bridge = _load_base(base)
        result = _run_custom_materializer(
            bridge=bridge,
            tile=tile,
            tile_inputs=["I0", "CLK"],
            tile_outputs=["Q0"],
            lanes=[
                {
                    "data_port": "I0",
                    "output_port": "Q0",
                    "clock_port": "CLK",
                    "depth_options": [
                        {
                            "depth": 3,
                            "mode_config": {
                                "ConfigBits[0]": 0,
                                "ConfigBits[1]": 1,
                            },
                        },
                        {
                            "depth": 2,
                            "mode_config": {
                                "ConfigBits[0]": 1,
                                "ConfigBits[1]": 0,
                            },
                        },
                    ],
                }
            ],
            tile_config_prefixes=["ConfigBits"],
        )

        assert result.result_data is not None
        assert result.result_data.stats.materialized_ffs == 5
        assert result.result_data.stats.inserted_tiles == 2
        assert "depth 3: 1" in result.result_data.report_summary
        assert "depth 2: 1" in result.result_data.report_summary
        cells = bridge.to_netlist_dict()["modules"]["base"]["cells"]
        assert len(_cells_by_type(cells, "configurable_depth_tile")) == 2
        assert not _has_cell_type(cells, "$dff")
        _assert_equivalent(base=base, gate_bridge=bridge, tile=tile, seq_depth=7)


def test_auto_config_depth_mode_solves_identity() -> None:
    """Test auto_config uses depth mode config while solving identity."""
    with TemporaryDirectory(prefix="ff_mat_auto_depth_") as td:
        tmp_dir = Path(td)
        base = _write_pipeline_base(tmp_dir, depth=2)
        tile = _write_auto_depth_tile(tmp_dir)

        bridge = _load_base(base)
        result = _run_custom_materializer(
            bridge=bridge,
            tile=tile,
            tile_inputs=["I0", "CLK"],
            tile_outputs=["Q0"],
            lanes=[
                {
                    "data_port": "I0",
                    "output_port": "Q0",
                    "clock_port": "CLK",
                    "depth_options": [
                        {
                            "depth": 2,
                            "mode_config": {"ConfigBits[2]": 1},
                        }
                    ],
                }
            ],
            tile_config_prefixes=["ConfigBits"],
            auto_config=True,
        )

        assert result.result_data is not None
        assert result.result_data.stats.materialized_ffs == 2
        cells = bridge.to_netlist_dict()["modules"]["base"]["cells"]
        tile_cell = _cells_by_type(cells, "auto_depth_tile")[0]
        assert tile_cell["connections"]["ConfigBits"][2] == "1"
        assert not _has_cell_type(cells, "$dff")
        _assert_equivalent(base=base, gate_bridge=bridge, tile=tile, seq_depth=4)


def test_depth_mode_config_conflict_splits_tiles() -> None:
    """Test incompatible depth mode configs cannot share one tile."""
    with TemporaryDirectory(prefix="ff_mat_depth_mode_conflict_") as td:
        tmp_dir = Path(td)
        base = _write_two_dff_base(tmp_dir)
        tile = _write_tile(tmp_dir)

        bridge = _load_base(base)
        result = _run_custom_materializer(
            bridge=bridge,
            tile=tile,
            tile_inputs=["I0", "I1", "CLK", "EN", "SR"],
            tile_outputs=["Q0", "Q1"],
            lanes=[
                {
                    "data_port": "I0",
                    "output_port": "Q0",
                    "clock_port": "CLK",
                    "depth_options": [
                        {"depth": 1, "mode_config": {"ConfigBits[2]": 1}}
                    ],
                },
                {
                    "data_port": "I1",
                    "output_port": "Q1",
                    "clock_port": "CLK",
                    "depth_options": [
                        {"depth": 1, "mode_config": {"ConfigBits[2]": 0}}
                    ],
                },
            ],
            tile_config_prefixes=["ConfigBits"],
        )

        assert result.result_data is not None
        assert result.result_data.stats.materialized_ffs == 2
        assert result.result_data.stats.inserted_tiles == 2


def test_depth_larger_than_chain_fails_when_requested() -> None:
    """Test a lane that only supports depth two cannot consume one FF."""
    with TemporaryDirectory(prefix="ff_mat_depth_too_large_") as td:
        tmp_dir = Path(td)
        base = _write_single_dff_base(tmp_dir)
        tile = _write_configurable_depth_tile(tmp_dir)

        bridge = _load_base(base)
        error_message = ""
        try:
            _run_custom_materializer(
                bridge=bridge,
                tile=tile,
                tile_inputs=["I0", "CLK"],
                tile_outputs=["Q0"],
                lanes=[
                    {
                        "data_port": "I0",
                        "output_port": "Q0",
                        "clock_port": "CLK",
                        "depth_options": [
                            {
                                "depth": 2,
                                "mode_config": {
                                    "ConfigBits[0]": 1,
                                    "ConfigBits[1]": 0,
                                },
                            }
                        ],
                    }
                ],
                tile_config_prefixes=["ConfigBits"],
                fail_on_unmaterialized_ff=True,
            )
        except RuntimeError as exc:
            error_message = str(exc)
        if not error_message:
            raise AssertionError("expected unsupported depth to leave FF unmapped")
        assert "left supported FFs unreplaced" in error_message


def test_depth_chain_with_intermediate_fanout_is_not_collapsed() -> None:
    """Test depth tracing refuses to collapse across intermediate fanout."""
    with TemporaryDirectory(prefix="ff_mat_depth_fanout_") as td:
        tmp_dir = Path(td)
        base = _write_pipeline_with_fanout_base(tmp_dir)
        tile = _write_configurable_depth_tile(tmp_dir)

        bridge = _load_base(base)
        error_message = ""
        try:
            _run_custom_materializer(
                bridge=bridge,
                tile=tile,
                tile_inputs=["I0", "CLK"],
                tile_outputs=["Q0"],
                lanes=[
                    {
                        "data_port": "I0",
                        "output_port": "Q0",
                        "clock_port": "CLK",
                        "depth_options": [
                            {
                                "depth": 2,
                                "mode_config": {
                                    "ConfigBits[0]": 1,
                                    "ConfigBits[1]": 0,
                                },
                            }
                        ],
                    }
                ],
                tile_config_prefixes=["ConfigBits"],
                fail_on_unmaterialized_ff=True,
            )
        except RuntimeError as exc:
            error_message = str(exc)
        if not error_message:
            raise AssertionError("expected fanout chain to remain unmapped")
        assert "left supported FFs unreplaced" in error_message


def test_fail_on_unmaterialized_ff_raises() -> None:
    """Test a leftover supported FF can be turned into a hard error."""
    with TemporaryDirectory(prefix="ff_mat_fail_unmaterialized_") as td:
        tmp_dir = Path(td)
        base = _write_dffe_base(tmp_dir)
        tile = _write_tile(tmp_dir)

        bridge = _load_base(base)
        error_message = ""
        try:
            _run_materializer(
                bridge=bridge,
                tile=tile,
                pack=True,
                include_enable=False,
                fail_on_unmaterialized_ff=True,
            )
        except RuntimeError as exc:
            error_message = str(exc)
        if not error_message:
            raise AssertionError("expected leftover FF to fail")
        assert "left supported FFs unreplaced" in error_message


def test_fail_on_invalid_lane_false_ignores_bad_lane() -> None:
    """Test invalid lanes can be ignored when explicitly requested."""
    with TemporaryDirectory(prefix="ff_mat_ignore_bad_lane_") as td:
        tmp_dir = Path(td)
        base = _write_single_dff_base(tmp_dir)
        tile = _write_auto_config_tile(tmp_dir)

        bridge = _load_base(base)
        result = _run_auto_materializer(
            bridge=bridge,
            tile=tile,
            auto_config=False,
            fail_on_invalid_lane=False,
            lanes=[
                {
                    "data_port": "DOES_NOT_EXIST",
                    "output_port": "Q0",
                    "clock_port": "CLK",
                },
                {
                    "data_port": "I0",
                    "output_port": "Q0",
                    "clock_port": "CLK",
                },
            ],
        )

        assert result.result_data is not None
        assert result.result_data.stats.materialized_ffs == 1


def _run_materializer(
    bridge: PyosysBridge,
    tile: Path,
    pack: bool,
    include_enable: bool = True,
    include_reset: bool = False,
    max_replacements: int | None = None,
    second_lane_config: dict[str, int | bool] | None = None,
    fail_on_pack_conflict: bool = False,
    fail_on_unmaterialized_ff: bool = False,
) -> FfMaterializerPass:
    """Run the materializer pass with a common two-lane tile.

    Parameters
    ----------
    bridge : PyosysBridge
        Design bridge to mutate.
    tile : Path
        Tile Verilog path.
    pack : bool
        Whether packing is enabled.
    include_enable : bool
        Whether lanes accept enabled FFs.
    include_reset : bool
        Whether lanes accept reset FFs.
    max_replacements : int | None
        Optional replacement cap.
    second_lane_config : dict[str, int | bool] | None
        Optional second-lane config override.
    fail_on_pack_conflict : bool
        Whether config, parameter, or port packing conflicts should raise.
    fail_on_unmaterialized_ff : bool
        Whether leftover supported FFs should raise.

    Returns
    -------
    FfMaterializerPass
        Executed pass.
    """
    result = FfMaterializerPass(
        tile_verilog_path=tile,
        tile_top_name="reg_tile",
        tile_inputs=["I0", "I1", "CLK", "EN", "SR"],
        tile_outputs=["Q0", "Q1"],
        tile_config_prefixes=["ConfigBits"],
        lanes=[
            {
                "data_port": "I0",
                "output_port": "Q0",
                "clock_port": "CLK",
                "include_enable_ff": include_enable,
                "enable_tile_port": "EN",
                "enable_neutral": 1,
                "include_reset_ff": include_reset,
                "reset_tile_port": "SR",
                "reset_neutral": 0,
                "reset_kind": "sync",
                "reset_value": 0,
                "config": {"ConfigBits[2]": 1},
                "params": {"MODE": "ff_only"},
            },
            {
                "data_port": "I1",
                "output_port": "Q1",
                "clock_port": "CLK",
                "include_enable_ff": include_enable,
                "enable_tile_port": "EN",
                "enable_neutral": 1,
                "include_reset_ff": include_reset,
                "reset_tile_port": "SR",
                "reset_neutral": 0,
                "reset_kind": "sync",
                "reset_value": 0,
                "config": second_lane_config or {"ConfigBits[3]": 1},
                "params": {"MODE": "ff_only"},
            },
        ],
        pack_multiple_ffs_per_tile=pack,
        max_replacements=max_replacements,
        fail_on_pack_conflict=fail_on_pack_conflict,
        fail_on_unmaterialized_ff=fail_on_unmaterialized_ff,
        top_name="base",
        track_progress=False,
    )
    result.run_on(bridge)
    return result


def _run_auto_materializer(
    bridge: PyosysBridge,
    tile: Path,
    lanes: list[dict[str, object]],
    tile_inputs: list[str] | None = None,
    auto_config: bool = False,
    auto_config_overwrites: dict[str, int | bool] | None = None,
    fail_on_invalid_lane: bool = True,
    fail_on_auto_config_unsat: bool = False,
) -> FfMaterializerPass:
    """Run the materializer with custom auto-config lanes.

    Parameters
    ----------
    bridge : PyosysBridge
        Design bridge to mutate.
    tile : Path
        Tile Verilog path.
    lanes : list[dict[str, object]]
        Lane payloads passed to the pass.
    tile_inputs : list[str] | None
        Optional tile inputs. ``None`` selects the common auto-config test
        ports.
    auto_config : bool
        Whether to solve a global identity config for each packed lane set.
    auto_config_overwrites : dict[str, int | bool] | None
        Fixed config constraints used by global auto-config.
    fail_on_invalid_lane : bool
        Whether invalid lane definitions should raise.
    fail_on_auto_config_unsat : bool
        Whether unsatisfiable auto-config attempts should raise.

    Returns
    -------
    FfMaterializerPass
        Executed pass.
    """
    result = FfMaterializerPass(
        tile_verilog_path=tile,
        tile_top_name=_tile_top_from_path(tile),
        tile_inputs=tile_inputs or ["I0", "I1", "CLK"],
        tile_outputs=["Q0", "Q1"],
        tile_config_prefixes=["ConfigBits"],
        lanes=lanes,
        pack_multiple_ffs_per_tile=True,
        auto_config=auto_config,
        auto_config_overwrites=auto_config_overwrites,
        fail_on_invalid_lane=fail_on_invalid_lane,
        fail_on_auto_config_unsat=fail_on_auto_config_unsat,
        top_name="base",
        track_progress=False,
    )
    result.run_on(bridge)
    return result


def _run_custom_materializer(
    bridge: PyosysBridge,
    tile: Path,
    tile_inputs: list[str],
    tile_outputs: list[str],
    lanes: list[dict[str, object]],
    tile_config_prefixes: list[str] | None = None,
    auto_config: bool = False,
    fail_on_unmaterialized_ff: bool = False,
) -> FfMaterializerPass:
    """Run the materializer with a custom tile shape.

    Parameters
    ----------
    bridge : PyosysBridge
        Design bridge to mutate.
    tile : Path
        Tile Verilog path.
    tile_inputs : list[str]
        Tile input ports exposed to the pass.
    tile_outputs : list[str]
        Tile output ports exposed to the pass.
    lanes : list[dict[str, object]]
        Lane payloads passed to the pass.
    tile_config_prefixes : list[str] | None
        Optional config prefixes exposed to the pass.
    auto_config : bool
        Whether SAT-fab should solve identity config for each replacement.
    fail_on_unmaterialized_ff : bool
        Whether leftover supported FFs should raise.

    Returns
    -------
    FfMaterializerPass
        Executed pass.
    """
    result = FfMaterializerPass(
        tile_verilog_path=tile,
        tile_top_name=_tile_top_from_path(tile),
        tile_inputs=tile_inputs,
        tile_outputs=tile_outputs,
        tile_config_prefixes=tile_config_prefixes,
        lanes=lanes,
        pack_multiple_ffs_per_tile=True,
        auto_config=auto_config,
        fail_on_unmaterialized_ff=fail_on_unmaterialized_ff,
        top_name="base",
        track_progress=False,
    )
    result.run_on(bridge)
    return result


def _load_base(base: Path) -> PyosysBridge:
    """Load and process a base design.

    Parameters
    ----------
    base : Path
        Base Verilog path.

    Returns
    -------
    PyosysBridge
        Processed design bridge.
    """
    bridge = PyosysBridge(debug=False)
    bridge.read_verilog_paths([base])
    bridge.run_pass("proc")
    return bridge


def _assert_equivalent(
    base: Path,
    gate_bridge: PyosysBridge,
    tile: Path,
    seq_depth: int = 2,
) -> None:
    """Run a small Yosys equivalence check against the original FF design.

    Parameters
    ----------
    base : Path
        Original base Verilog.
    gate_bridge : PyosysBridge
        Mutated gate design.
    tile : Path
        Tile implementation Verilog.
    seq_depth : int
        Sequential equivalence depth.
    """
    with TemporaryDirectory(prefix="ff_mat_equiv_") as td:
        gate = Path(td) / "gate.v"
        gate_bridge.write_verilog_path(gate)
        bridge = PyosysBridge(debug=False)
        bridge.read_verilog_paths([base])
        bridge.run_pass("proc")
        bridge.run_pass("rename base base_gold")
        bridge.read_verilog_paths([tile])
        bridge.run_pass("proc")
        bridge.run_pass(f"read_verilog -overwrite {gate}")
        bridge.run_pass("rename base base_gate")
        bridge.run_pass("equiv_make base_gold base_gate equiv")
        bridge.run_pass("hierarchy -top equiv")
        bridge.run_pass("proc")
        bridge.run_pass("flatten")
        bridge.run_pass("opt_clean")
        bridge.run_pass(f"equiv_simple -seq {seq_depth}")
        bridge.run_pass("equiv_status -assert")


def _write_sequential_input_tile(tmp_dir: Path, count: int) -> Path:
    """Write a tile where each exposed output is driven by an input register.

    Parameters
    ----------
    tmp_dir : Path
        Directory for the generated file.
    count : int
        Number of one-bit input-side register lanes.

    Returns
    -------
    Path
        Generated Verilog path.
    """
    path = tmp_dir / f"seq_input_tile_{count}.v"
    input_ports = "\n".join(f"  input I{index}," for index in range(count))
    output_ports = "\n".join(
        f"  output O{index}{',' if index + 1 < count else ''}" for index in range(count)
    )
    regs = "\n".join(f"  reg R{index};" for index in range(count))
    updates = "\n".join(f"    R{index} <= I{index};" for index in range(count))
    assigns = "\n".join(f"  assign O{index} = R{index};" for index in range(count))
    path.write_text(
        f"""
module seq_input_tile_{count} (
{input_ports}
  input CLK,
{output_ports}
);
{regs}
  always @(posedge CLK) begin
{updates}
  end
{assigns}
endmodule
""",
        encoding="utf-8",
    )
    return path


def _write_mixed_sequential_tile(tmp_dir: Path) -> Path:
    """Write a five-lane tile with input-side and output-side registers.

    Parameters
    ----------
    tmp_dir : Path
        Directory for the generated file.

    Returns
    -------
    Path
        Generated Verilog path.
    """
    path = tmp_dir / "mixed_sequential_tile.v"
    path.write_text(
        """
module mixed_sequential_tile (
  input I0,
  input I1,
  input I2,
  input I3,
  input I4,
  input CLK,
  output O0,
  output reg Q1,
  output O2,
  output reg Q3,
  output reg Q4
);
  reg R0;
  reg R2;
  always @(posedge CLK) begin
    R0 <= I0;
    Q1 <= I1;
    R2 <= I2;
    Q3 <= I3;
    Q4 <= I4;
  end
  assign O0 = R0;
  assign O2 = R2;
endmodule
""",
        encoding="utf-8",
    )
    return path


def _write_configurable_depth_tile(tmp_dir: Path) -> Path:
    """Write a single-lane tile with selectable pipeline depth.

    Parameters
    ----------
    tmp_dir : Path
        Directory for the generated file.

    Returns
    -------
    Path
        Generated Verilog path.
    """
    path = tmp_dir / "configurable_depth_tile.v"
    path.write_text(
        """
module configurable_depth_tile (
  input I0,
  input CLK,
  input [1:0] ConfigBits,
  output reg Q0
);
  reg R0;
  reg R1;
  always @(posedge CLK) begin
    R0 <= I0;
    R1 <= R0;
    case (ConfigBits)
      2'b00: Q0 <= I0;
      2'b01: Q0 <= R0;
      2'b10: Q0 <= R1;
      default: Q0 <= 1'b0;
    endcase
  end
endmodule
""",
        encoding="utf-8",
    )
    return path


def _write_auto_depth_tile(tmp_dir: Path) -> Path:
    """Write a depth-two tile whose identity path needs SAT config.

    Parameters
    ----------
    tmp_dir : Path
        Directory for the generated file.

    Returns
    -------
    Path
        Generated Verilog path.
    """
    path = tmp_dir / "auto_depth_tile.v"
    path.write_text(
        """
module auto_depth_tile (
  input I0,
  input CLK,
  input [2:0] ConfigBits,
  output reg Q0
);
  reg R0;
  wire first = ConfigBits[0] ? I0 : ~I0;
  wire second = ConfigBits[1] ? R0 : ~R0;
  always @(posedge CLK) begin
    R0 <= first;
    Q0 <= ConfigBits[2] ? second : I0;
  end
endmodule
""",
        encoding="utf-8",
    )
    return path


def _write_tile(tmp_dir: Path) -> Path:
    """Write a two-lane configurable tile model.

    Parameters
    ----------
    tmp_dir : Path
        Directory for the generated file.

    Returns
    -------
    Path
        Generated Verilog path.
    """
    path = tmp_dir / "reg_tile.v"
    path.write_text(
        """
module reg_tile #(
  parameter MODE = "comb"
) (
  input I0,
  input I1,
  input CLK,
  input EN,
  input SR,
  input [7:0] ConfigBits,
  output Q0,
  output Q1
);
  assign Q0 = I0 ^ ConfigBits[0];
  assign Q1 = I1 ^ ConfigBits[1];
endmodule
""",
        encoding="utf-8",
    )
    return path


def _write_auto_config_tile(tmp_dir: Path) -> Path:
    """Write a tile whose register data path needs one config bit."""
    path = tmp_dir / "auto_reg_tile.v"
    path.write_text(
        """
module auto_reg_tile (
  input I0,
  input I1,
  input CLK,
  input [1:0] ConfigBits,
  output reg Q0,
  output Q1
);
  wire d0 = ConfigBits[0] ? I0 : ~I0;
  always @(posedge CLK) Q0 <= d0;
  assign Q1 = I1;
endmodule
""",
        encoding="utf-8",
    )
    return path


def _write_auto_config_constraint_tile(tmp_dir: Path) -> Path:
    """Write a tile needing a fixed mode bit and one SAT-solved bit."""
    path = tmp_dir / "auto_constraint_tile.v"
    path.write_text(
        """
module auto_constraint_tile (
  input I0,
  input I1,
  input CLK,
  input [1:0] ConfigBits,
  output reg Q0,
  output Q1
);
  wire enabled = ConfigBits[0];
  wire d0 = enabled ? (ConfigBits[1] ? I0 : ~I0) : 1'b0;
  always @(posedge CLK) Q0 <= d0;
  assign Q1 = I1;
endmodule
""",
        encoding="utf-8",
    )
    return path


def _write_auto_priority_mux_tile(tmp_dir: Path) -> Path:
    """Write a tile whose control flow emits a Yosys priority mux."""
    path = tmp_dir / "auto_priority_mux_tile.v"
    path.write_text(
        """
module auto_priority_mux_tile (
  input I0,
  input I1,
  input CLK,
  input [1:0] ConfigBits,
  output reg Q0,
  output Q1
);
  reg d0;
  always @* begin
    d0 = ~I0;
    casez (ConfigBits)
      2'b?1: d0 = I0;
      2'b1?: d0 = 1'b0;
    endcase
  end
  always @(posedge CLK) Q0 <= d0;
  assign Q1 = I1;
endmodule
""",
        encoding="utf-8",
    )
    return path


def _write_auto_config_external_input_tile(tmp_dir: Path) -> Path:
    """Write a tile whose selected output cone references another tile input."""
    path = tmp_dir / "auto_external_input_tile.v"
    path.write_text(
        """
module auto_external_input_tile (
  input I0,
  input I1,
  input CLK,
  input ConfigBits,
  output reg Q0,
  output Q1
);
  wire d0 = ConfigBits ? I0 : I1;
  always @(posedge CLK) Q0 <= d0;
  assign Q1 = I1;
endmodule
""",
        encoding="utf-8",
    )
    return path


def _write_auto_config_controlled_tile(tmp_dir: Path) -> Path:
    """Write a tile with shared enable/reset controls on registered outputs."""
    path = tmp_dir / "auto_controlled_tile.v"
    path.write_text(
        """
module auto_controlled_tile (
  input I0,
  input I1,
  input CLK,
  input EN,
  input SR,
  input ConfigBits,
  output reg Q0,
  output reg Q1
);
  wire d0 = ConfigBits ? I0 : ~I0;
  wire d1 = I1;
  always @(posedge CLK) begin
    if (EN) begin
      if (SR) begin
        Q0 <= 1'b0;
        Q1 <= 1'b0;
      end else begin
        Q0 <= d0;
        Q1 <= d1;
      end
    end
  end
endmodule
""",
        encoding="utf-8",
    )
    return path


def _write_auto_config_independent_control_tile(tmp_dir: Path) -> Path:
    """Write a tile with independent enable/reset controls per output."""
    path = tmp_dir / "auto_independent_control_tile.v"
    path.write_text(
        """
module auto_independent_control_tile (
  input I0,
  input I1,
  input CLK,
  input EN0,
  input SR0,
  input EN1,
  input SR1,
  input ConfigBits,
  output reg Q0,
  output reg Q1
);
  wire d0 = ConfigBits ? I0 : ~I0;
  wire d1 = ConfigBits ? I1 : ~I1;
  always @(posedge CLK) begin
    if (EN0) begin
      if (SR0) Q0 <= 1'b0;
      else Q0 <= d0;
    end
    if (EN1) begin
      if (SR1) Q1 <= 1'b0;
      else Q1 <= d1;
    end
  end
endmodule
""",
        encoding="utf-8",
    )
    return path


def _write_auto_pack_conflict_tile(tmp_dir: Path) -> Path:
    """Write a two-lane tile whose lanes need conflicting config values."""
    path = tmp_dir / "auto_pack_conflict_tile.v"
    path.write_text(
        """
module auto_pack_conflict_tile (
  input I0,
  input I1,
  input CLK,
  input ConfigBits,
  output reg Q0,
  output reg Q1
);
  always @(posedge CLK) begin
    Q0 <= ConfigBits ? I0 : ~I0;
    Q1 <= ConfigBits ? ~I1 : I1;
  end
endmodule
""",
        encoding="utf-8",
    )
    return path


def _write_auto_shared_solution_tile(tmp_dir: Path) -> Path:
    """Write a two-lane tile needing one shared identity config."""
    path = tmp_dir / "auto_shared_solution_tile.v"
    path.write_text(
        """
module auto_shared_solution_tile (
  input I0,
  input I1,
  input CLK,
  input ConfigBits,
  output reg Q0,
  output reg Q1
);
  always @(posedge CLK) begin
    Q0 <= I0;
    Q1 <= ConfigBits ? I1 : ~I1;
  end
endmodule
""",
        encoding="utf-8",
    )
    return path


def _tile_top_from_path(tile: Path) -> str:
    """Return the test tile top name for a generated tile path."""
    return tile.stem


def _write_single_dff_base(tmp_dir: Path) -> Path:
    """Write a design with one inferred DFF.

    Parameters
    ----------
    tmp_dir : Path
        Directory for the generated file.

    Returns
    -------
    Path
        Generated Verilog path.
    """
    path = tmp_dir / "base_single.v"
    path.write_text(
        """
module base(input clk, input d, output reg q);
  always @(posedge clk) q <= d;
endmodule
""",
        encoding="utf-8",
    )
    return path


def _write_two_dff_base(tmp_dir: Path) -> Path:
    """Write a design with two independent inferred DFFs."""
    path = tmp_dir / "base_two.v"
    path.write_text(
        """
module base(input clk, input d0, input d1, output reg q0, output reg q1);
  always @(posedge clk) begin
    q0 <= d0;
    q1 <= d1;
  end
endmodule
""",
        encoding="utf-8",
    )
    return path


def _write_many_dff_base(tmp_dir: Path, count: int) -> Path:
    """Write a design with ``count`` independent inferred DFFs.

    Parameters
    ----------
    tmp_dir : Path
        Directory for the generated file.
    count : int
        Number of one-bit FFs to infer.

    Returns
    -------
    Path
        Generated Verilog path.
    """
    path = tmp_dir / f"base_{count}_dff.v"
    inputs = ", ".join(f"input d{index}" for index in range(count))
    outputs = ", ".join(f"output reg q{index}" for index in range(count))
    updates = "\n".join(f"    q{index} <= d{index};" for index in range(count))
    path.write_text(
        f"""
module base(input clk, {inputs}, {outputs});
  always @(posedge clk) begin
{updates}
  end
endmodule
""",
        encoding="utf-8",
    )
    return path


def _write_chain_base(tmp_dir: Path) -> Path:
    """Write a design with a two-FF pipeline."""
    path = tmp_dir / "base_chain.v"
    path.write_text(
        """
module base(input clk, input d, output q0, output q1);
  reg r0;
  reg r1;
  assign q0 = r0;
  assign q1 = r1;
  always @(posedge clk) begin
    r0 <= d;
    r1 <= r0;
  end
endmodule
""",
        encoding="utf-8",
    )
    return path


def _write_pipeline_base(tmp_dir: Path, depth: int) -> Path:
    """Write a linear FF pipeline with only the final output exposed.

    Parameters
    ----------
    tmp_dir : Path
        Directory for the generated file.
    depth : int
        Number of pipeline FFs.

    Returns
    -------
    Path
        Generated Verilog path.
    """
    path = tmp_dir / f"base_pipeline_{depth}.v"
    regs = "\n".join(f"  reg r{index};" for index in range(depth))
    updates = ["    r0 <= d;"]
    updates.extend(f"    r{index} <= r{index - 1};" for index in range(1, depth))
    path.write_text(
        f"""
module base(input clk, input d, output q);
{regs}
  assign q = r{depth - 1};
  always @(posedge clk) begin
{chr(10).join(updates)}
  end
endmodule
""",
        encoding="utf-8",
    )
    return path


def _write_pipeline_with_fanout_base(tmp_dir: Path) -> Path:
    """Write a two-FF chain whose intermediate net has combinational fanout.

    Parameters
    ----------
    tmp_dir : Path
        Directory for the generated file.

    Returns
    -------
    Path
        Generated Verilog path.
    """
    path = tmp_dir / "base_pipeline_fanout.v"
    path.write_text(
        """
module base(input clk, input d, input side, output q, output tap);
  reg r0;
  reg r1;
  assign tap = r0 & side;
  assign q = r1;
  always @(posedge clk) begin
    r0 <= d;
    r1 <= r0;
  end
endmodule
""",
        encoding="utf-8",
    )
    return path


def _write_dffe_base(tmp_dir: Path) -> Path:
    """Write a design with an explicit Yosys ``$dffe`` cell."""
    path = tmp_dir / "base_dffe.v"
    path.write_text(
        """
module base(input clk, input en, input d, output q);
  \\$dffe #(
    .WIDTH(1),
    .CLK_POLARITY(1'b1),
    .EN_POLARITY(1'b1)
  ) u_ff (
    .CLK(clk),
    .EN(en),
    .D(d),
    .Q(q)
  );
endmodule
""",
        encoding="utf-8",
    )
    return path


def _write_sdff_base(tmp_dir: Path, reset_value: int) -> Path:
    """Write a design with an explicit Yosys ``$sdff`` cell."""
    path = tmp_dir / "base_sdff.v"
    path.write_text(
        f"""
module base(input clk, input rst, input d, output q);
  \\$sdff #(
    .WIDTH(1),
    .CLK_POLARITY(1'b1),
    .SRST_POLARITY(1'b1),
    .SRST_VALUE(1'b{reset_value})
  ) u_ff (
    .CLK(clk),
    .SRST(rst),
    .D(d),
    .Q(q)
  );
endmodule
""",
        encoding="utf-8",
    )
    return path


def _write_escaped_base(tmp_dir: Path) -> Path:
    """Write a design with an escaped generated-style FF name."""
    path = tmp_dir / "base_escaped.v"
    path.write_text(
        """
module base(input clk, input d, output q);
  \\$dff #(
    .WIDTH(1),
    .CLK_POLARITY(1'b1)
  ) \\$auto$ff.materializer$1.slice[0]  (
    .CLK(clk),
    .D(d),
    .Q(q)
  );
endmodule
""",
        encoding="utf-8",
    )
    return path


def _cells_by_type(
    cells: dict[str, dict[str, object]],
    cell_type: str,
) -> list[dict[str, object]]:
    """Return cells with a selected type."""
    return [
        cell
        for cell in cells.values()
        if str(cell.get("type")).removeprefix("\\") == cell_type
    ]


def _has_cell_type(cells: dict[str, dict[str, object]], cell_type: str) -> bool:
    """Return whether a netlist dictionary contains a cell type."""
    return any(
        str(cell.get("type")).removeprefix("\\") == cell_type for cell in cells.values()
    )


def main() -> None:
    """Run all FF materializer tests."""
    test_single_dff_materialization()
    test_two_ffs_pack_into_one_tile()
    test_pack_disabled_creates_one_tile_per_ff()
    test_ff_chain_is_preserved_when_packed()
    test_dffe_with_variable_enable_is_skipped_by_default()
    test_dffe_enable_can_be_wired_to_tile()
    test_sdff_reset_can_be_wired_to_tile()
    test_reset_value_mismatch_is_skipped()
    test_config_conflict_prevents_packing_second_ff()
    test_fail_on_pack_conflict_raises()
    test_max_replacements_limits_materialization()
    test_escaped_ff_name_materialization()
    test_no_auto_config_replaces_without_config_updates()
    test_auto_config_solves_identity_config_and_is_equivalent()
    test_auto_config_uses_global_overwrites_as_constraint()
    test_auto_config_lowers_priority_mux_tile()
    test_auto_config_imports_all_candidate_inputs()
    test_auto_config_neutralizes_shared_register_controls()
    test_auto_config_neutralizes_independent_lane_controls()
    test_shared_enable_neutral_conflict_raises()
    test_shared_reset_setting_conflict_raises()
    test_auto_config_unsat_constraint_raises()
    test_auto_config_conflict_prevents_packing_second_ff()
    test_auto_config_fail_on_unsat_group_raises()
    test_auto_config_shared_solution_packs_two_ffs()
    test_auto_config_rejects_lane_local_config()
    test_single_sequential_input_lane_is_equivalent()
    test_two_sequential_input_lanes_pack_and_are_equivalent()
    test_five_sequential_input_lanes_pack_and_are_equivalent()
    test_mixed_sequential_input_and_output_lanes_are_equivalent()
    test_manual_depth_two_lane_replaces_two_ff_chain()
    test_manual_configurable_depth_chunks_long_chain()
    test_auto_config_depth_mode_solves_identity()
    test_depth_mode_config_conflict_splits_tiles()
    test_depth_larger_than_chain_fails_when_requested()
    test_depth_chain_with_intermediate_fanout_is_not_collapsed()
    test_fail_on_unmaterialized_ff_raises()
    test_fail_on_invalid_lane_false_ignores_bad_lane()


if __name__ == "__main__":
    main()
