"""Tests for routing-demand evaluation."""

from __future__ import annotations

from pathlib import Path
from random import Random
from tempfile import TemporaryDirectory
from typing import TYPE_CHECKING

from fabulous.fabric_cad.fabxplore.modules.routing_demand_evaluator import (
    RoutingDemandEvaluator,
    RoutingDemandEvaluatorOptions,
)
from fabulous.fabric_cad.fabxplore.modules.routing_demand_evaluator.core.evaluator import (  # noqa: E501
    build_graph,
)
from fabulous.fabric_cad.fabxplore.modules.routing_demand_evaluator.core.matrix_loader import (  # noqa: E501
    load_matrix_data,
)
from fabulous.fabric_cad.fabxplore.modules.routing_demand_evaluator.core.models import (
    DemandClassName,
    DemandKind,
    DemandProfileName,
    OptimizerName,
    RoutingDemand,
    RoutingTerminalRole,
)
from fabulous.fabric_cad.fabxplore.modules.routing_demand_evaluator.core.routing_graph import (  # noqa: E501
    RoutingGraph,
)
from fabulous.fabric_cad.fabxplore.modules.routing_demand_evaluator.demand_classes import (  # noqa: E501
    access,
    carry,
    fanout,
    random,
    routing,
)
from fabulous.fabric_cad.fabxplore.modules.routing_demand_evaluator.optimizers.greedy.optimizer import (  # noqa: E501
    _remove_emptying_pips,
    _render_list,
)
from fabulous.fabric_cad.fabxplore.modules.routing_demand_evaluator.routers.pathfinder import (  # noqa: E501
    PathFinderRouter,
)
from fabulous.fabric_cad.fabxplore.pnr.custom_passes.routing_demand_evaluator_pass import (  # noqa: E501
    RoutingDemandEvaluatorPass,
)
from fabulous.fabric_definition.bel import Bel
from fabulous.fabric_definition.define import IO
from fabulous.fabric_generator.parser.parse_csv import parsePortLine
from fabulous.fabric_generator.parser.parse_switchmatrix import parseList
from fabulous.fabulous_cli.helper import setup_logger

if TYPE_CHECKING:
    from fabulous.fabric_definition.port import Port

setup_logger(verbosity=0, debug=False)


class _FakeTile:
    """Minimal FABulous tile test double."""

    def __init__(
        self,
        name: str,
        tile_csv: Path,
        matrix: Path,
        ports: list[Port] | None = None,
        bels: list[Bel] | None = None,
    ) -> None:
        self.name = name
        self.tileDir = tile_csv
        self.matrixDir = matrix
        self.portsInfo = ports or []
        self.bels = bels or []
        self.matrixConfigBits = 1
        self.globalConfigBits = 2


class _FakeFabric:
    """Minimal FABulous fabric test double."""

    def __init__(self, tile: _FakeTile) -> None:
        self.tile = tile
        self.frameBitsPerRow = 8
        self.maxFramesPerCol = 8

    def getTileByName(self, tile_name: str) -> _FakeTile | None:
        """Return the fake tile.

        Parameters
        ----------
        tile_name : str
            Tile name.

        Returns
        -------
        _FakeTile | None
            Fake tile or ``None``.
        """
        return self.tile if tile_name == self.tile.name else None


class _FakeFab:
    """Minimal FABulous API test double."""

    def __init__(self, tile: _FakeTile) -> None:
        self.fabric = _FakeFabric(tile)
        self.fileExtension = ".v"
        self._writer_output_file: Path | None = None

    def loadFabric(self, fabric_csv: Path) -> None:
        """Pretend to reload a FABulous fabric.

        Parameters
        ----------
        fabric_csv : Path
            Fabric CSV path.
        """
        _ = fabric_csv

    def setWriterOutputFile(self, output_file: Path) -> None:
        """Remember the requested writer output file.

        Parameters
        ----------
        output_file : Path
            Requested output file.
        """
        self._writer_output_file = output_file

    def genSwitchMatrix(self, tile_name: str) -> None:
        """Pretend to regenerate a switch matrix.

        Parameters
        ----------
        tile_name : str
            Tile name.
        """
        _ = tile_name

    def genConfigMem(self, tile_name: str, config_mem_csv: Path) -> None:
        """Pretend to regenerate config memory.

        Parameters
        ----------
        tile_name : str
            Tile name.
        config_mem_csv : Path
            Config-memory CSV path.
        """
        _ = tile_name
        _ = config_mem_csv

    def genTile(self, tile_name: str) -> None:
        """Pretend to regenerate a tile wrapper.

        Parameters
        ----------
        tile_name : str
            Tile name.
        """
        _ = tile_name


def test_models_validate_public_options() -> None:
    """Test option validation catches invalid public inputs."""
    _assert_raises_contains(
        lambda: RoutingDemandEvaluatorOptions(tile_name=""),
        "tile_name",
    )
    _assert_raises_contains(
        lambda: RoutingDemandEvaluatorOptions(
            tile_name="t",
            random_demand_ratio=1.5,
        ),
        "between",
    )
    disabled_opt = RoutingDemandEvaluatorOptions(
        tile_name="t",
        opt=False,
        optimizer="greedy",
    )
    assert disabled_opt.optimizer == OptimizerName.NONE
    power_mux = RoutingDemandEvaluatorOptions(
        tile_name="t",
        opt=True,
        optimizer="greedy",
        opt_power_of_two_muxes=True,
    )
    assert power_mux.opt_clean_mux is True


def test_matrix_loader_reads_list_and_jump_edges() -> None:
    """Test matrix loading uses FABulous parsers and expands JUMP resources."""
    with _project("jump_tile") as tile_dir:
        matrix = tile_dir / "jump_tile_switch_matrix.list"
        matrix.write_text("{2}J0_BEG0,[A|B]\nOUT,J0_END0\n", encoding="utf-8")
        tile_csv = _write_tile_csv(
            tile_dir,
            "jump_tile",
            matrix.name,
            extra_rows=["JUMP,J0_BEG,0,0,J0_END,1,"],
        )
        fab = _FakeFab(_FakeTile("jump_tile", tile_csv, matrix))

        data = load_matrix_data(
            RoutingDemandEvaluatorOptions(tile_name="jump_tile"),
            fab,  # type: ignore[arg-type]
        )

        assert data.connections["J0_BEG0"] == ["A", "B"]
        assert ("J0_BEG0", "J0_END0") in data.jump_edges
        assert data.config_capacity == 64


def test_matrix_loader_skips_source_less_jump_resources() -> None:
    """Test source-less JUMP resources are not treated as routable edges."""
    with _project("constant_tile") as tile_dir:
        matrix = tile_dir / "constant_tile_switch_matrix.list"
        matrix.write_text("OUT,A\n", encoding="utf-8")
        tile_csv = _write_tile_csv(
            tile_dir,
            "constant_tile",
            matrix.name,
            extra_rows=["JUMP,NULL,0,0,GND,1,"],
        )
        fab = _FakeFab(_FakeTile("constant_tile", tile_csv, matrix))

        data = load_matrix_data(
            RoutingDemandEvaluatorOptions(tile_name="constant_tile"),
            fab,  # type: ignore[arg-type]
        )

        assert data.jump_edges == []


def test_matrix_loader_classifies_fabulous_terminals() -> None:
    """Test terminal roles are derived from FABulous objects."""
    with _project("role_tile") as tile_dir:
        matrix = tile_dir / "role_tile_switch_matrix.list"
        matrix.write_text(
            "I,A0\nRST,A0\nEN,A0\nCi,Co\nOUT0,O\n",
            encoding="utf-8",
        )
        tile_csv = _write_tile_csv(tile_dir, "role_tile", matrix.name)
        fab = _FakeFab(
            _FakeTile(
                "role_tile",
                tile_csv,
                matrix,
                ports=_simple_ports(),
                bels=[_feature_bel(tile_dir)],
            )
        )

        data = load_matrix_data(
            RoutingDemandEvaluatorOptions(tile_name="role_tile"),
            fab,  # type: ignore[arg-type]
        )

        roles = {(terminal.name, terminal.role) for terminal in data.terminals}
        assert ("I", RoutingTerminalRole.BEL_INPUT) in roles
        assert ("O", RoutingTerminalRole.BEL_OUTPUT) in roles
        assert ("Ci", RoutingTerminalRole.CARRY_INPUT) in roles
        assert ("Co", RoutingTerminalRole.CARRY_OUTPUT) in roles
        assert ("RST", RoutingTerminalRole.LOCAL_RESET) in roles
        assert ("EN", RoutingTerminalRole.LOCAL_ENABLE) in roles


def test_matrix_loader_classifies_tile_carry_ports_from_csv() -> None:
    """Test carry-annotated tile ports are classified as carry terminals."""
    with _project("carry_tile") as tile_dir:
        matrix = tile_dir / "carry_tile_switch_matrix.list"
        matrix.write_text("Ci0,Co0\nN_ROW0,N_SRC0\n", encoding="utf-8")
        tile_csv = _write_tile_csv(
            tile_dir,
            "carry_tile",
            matrix.name,
            extra_rows=['NORTH,Co,0,-1,Ci,1,CARRY="C0"'],
        )
        fab = _FakeFab(
            _FakeTile(
                "carry_tile",
                tile_csv,
                matrix,
                ports=[*_carry_ports(), *_routing_ports()],
                bels=[],
            )
        )

        data = load_matrix_data(
            RoutingDemandEvaluatorOptions(tile_name="carry_tile"),
            fab,  # type: ignore[arg-type]
        )
        graph = build_graph(data)
        roles = {(terminal.name, terminal.role) for terminal in data.terminals}
        straight = routing.straight_routing(data, graph, limit=8, offset=0)
        carry_demands = carry.carry_chain(data, graph, limit=8, offset=0)

        assert ("Ci0", RoutingTerminalRole.CARRY_INPUT) in roles
        assert ("Co0", RoutingTerminalRole.CARRY_OUTPUT) in roles
        assert all(demand.source != "Ci0" for demand in straight)
        assert all(demand.sink != "Co0" for demand in straight)
        assert [(demand.source, demand.sink) for demand in carry_demands] == [
            ("Co0", "Ci0")
        ]


def test_carry_chain_uses_actual_matrix_carry_segments() -> None:
    """Test carry-chain demands follow explicit matrix carry PIPs."""
    with _project("carry_segments") as tile_dir:
        bel_a = Bel(
            src=tile_dir / "carry_a.v",
            prefix="LA_",
            module_name="carry",
            internal=[("LA_Ci", IO.INPUT), ("LA_Co", IO.OUTPUT)],
            external=[],
            configPort=[],
            sharedPort=[],
            configBit=0,
            belMap={},
            userCLK=False,
            ports_vectors={},
            carry={"C": {IO.INPUT: "LA_Ci", IO.OUTPUT: "LA_Co"}},
            localShared={},
        )
        bel_b = Bel(
            src=tile_dir / "carry_b.v",
            prefix="LB_",
            module_name="carry",
            internal=[("LB_Ci", IO.INPUT), ("LB_Co", IO.OUTPUT)],
            external=[],
            configPort=[],
            sharedPort=[],
            configBit=0,
            belMap={},
            userCLK=False,
            ports_vectors={},
            carry={"C": {IO.INPUT: "LB_Ci", IO.OUTPUT: "LB_Co"}},
            localShared={},
        )
        matrix = tile_dir / "carry_segments_switch_matrix.list"
        matrix.write_text(
            "\n".join(
                [
                    "LA_Ci,Ci0",
                    "LB_Ci,LA_Co",
                    "Co0,LB_Co",
                ]
            )
            + "\n",
            encoding="utf-8",
        )
        tile_csv = _write_tile_csv(
            tile_dir,
            "carry_segments",
            matrix.name,
            extra_rows=['NORTH,Co,0,-1,Ci,1,CARRY="C0"'],
        )
        fab = _FakeFab(
            _FakeTile(
                "carry_segments",
                tile_csv,
                matrix,
                ports=_carry_ports(),
                bels=[bel_a, bel_b],
            )
        )
        data = load_matrix_data(
            RoutingDemandEvaluatorOptions(tile_name="carry_segments"),
            fab,  # type: ignore[arg-type]
        )
        graph = build_graph(data)

        demands = carry.carry_chain(data, graph, limit=8, offset=0)

        assert [(demand.source, demand.sink) for demand in demands] == [
            ("Ci0", "LA_Ci"),
            ("LA_Co", "LB_Ci"),
            ("LB_Co", "Co0"),
        ]


def test_hierarchy_fed_single_fanin_bel_input_counts_as_generic() -> None:
    """Test one-source BEL rows remain generic when fed by a muxed JUMP."""
    with _project("hier_tile") as tile_dir:
        matrix = tile_dir / "hier_tile_switch_matrix.list"
        matrix.write_text("J0_BEG0,A0\nI,J0_END0\n", encoding="utf-8")
        tile_csv = _write_tile_csv(
            tile_dir,
            "hier_tile",
            matrix.name,
            extra_rows=["JUMP,J0_BEG,0,0,J0_END,1,"],
        )
        fab = _FakeFab(
            _FakeTile(
                "hier_tile",
                tile_csv,
                matrix,
                ports=_simple_ports(),
                bels=[_simple_bel(tile_dir)],
            )
        )
        data = load_matrix_data(
            RoutingDemandEvaluatorOptions(tile_name="hier_tile"),
            fab,  # type: ignore[arg-type]
        )
        graph = build_graph(data)

        demands = access.bel_input_reachability(data, graph, limit=8, offset=0)

        assert [(demand.source, demand.sink) for demand in demands] == [("A0", "I")]


def test_pathfinder_routes_through_jump_edge() -> None:
    """Test PathFinder can route through a generated JUMP edge."""
    graph = RoutingGraph.from_edges(
        [
            ("A", "J0_BEG0"),
            ("J0_BEG0", "J0_END0"),
            ("J0_END0", "OUT"),
        ]
    )
    demand = RoutingDemand(
        demand_id="d0",
        demand_class="manual",
        kind=DemandKind.HARD,
        source="A",
        sink="OUT",
    )
    result = PathFinderRouter(
        max_iterations=5,
        present_cost_multiplier=1.3,
        history_cost_increment=1.0,
    ).route(graph, [demand])

    assert result.demand_results[0].routed
    assert result.demand_results[0].path is not None
    assert result.demand_results[0].path.nodes == [
        "A",
        "J0_BEG0",
        "J0_END0",
        "OUT",
    ]


def test_pathfinder_routes_multi_sink_net() -> None:
    """Test PathFinder routes one net to multiple sinks."""
    graph = RoutingGraph.from_edges([("S", "A"), ("S", "B")])
    demand = RoutingDemand(
        demand_id="fanout0",
        demand_class="fanout",
        kind=DemandKind.SOFT,
        source="S",
        sink="A",
        sinks=["A", "B"],
    )
    result = PathFinderRouter(
        max_iterations=5,
        present_cost_multiplier=1.3,
        history_cost_increment=1.0,
    ).route(graph, [demand])

    assert result.demand_results[0].routed
    assert len(result.demand_results[0].paths) == 2
    assert result.router_stats.failed_sinks == 0


def test_evaluator_runs_minimal_profile() -> None:
    """Test end-to-end evaluator on a minimal profile."""
    with _project("eval_tile") as tile_dir:
        matrix = tile_dir / "eval_tile_switch_matrix.list"
        matrix.write_text("I,A0\nI,O\nOUT0,O\n", encoding="utf-8")
        tile_csv = _write_tile_csv(tile_dir, "eval_tile", matrix.name)
        fab = _FakeFab(
            _FakeTile(
                "eval_tile",
                tile_csv,
                matrix,
                ports=_simple_ports(),
                bels=[_simple_bel(tile_dir)],
            )
        )

        result = RoutingDemandEvaluator(
            RoutingDemandEvaluatorOptions(
                tile_name="eval_tile",
                demand_profile="minimal",
                demand_iterations=4,
                track_progress=False,
            )
        ).run(object(), fab)  # type: ignore[arg-type]

        assert result.stats.total_demands >= 2
        assert result.hard_demands_passed
        assert "Routing Demand Evaluator Report" in result.report_summary


def test_bel_output_escape_uses_matrix_destination_rows() -> None:
    """Test BEL escape demands target rows that list the BEL output."""
    with _project("escape_tile") as tile_dir:
        matrix = tile_dir / "escape_tile_switch_matrix.list"
        matrix.write_text(
            "I,N1BEG0\nROUTE_BEG,O\nDUMMY,N1END0\n",
            encoding="utf-8",
        )
        tile_csv = _write_tile_csv(tile_dir, "escape_tile", matrix.name)
        fab = _FakeFab(
            _FakeTile(
                "escape_tile",
                tile_csv,
                matrix,
                ports=_escape_ports(),
                bels=[_simple_bel(tile_dir)],
            )
        )
        data = load_matrix_data(
            RoutingDemandEvaluatorOptions(tile_name="escape_tile"),
            fab,  # type: ignore[arg-type]
        )
        graph = build_graph(data)

        demands = access.bel_output_escape(data, graph, limit=8, offset=0)
        actual = [(demand.source, demand.sink) for demand in demands]

        assert actual == [("O", "ROUTE_BEG")], (
            "BEL output escape must use matrix destination rows that list the "
            f"BEL output as a source, got {actual!r}"
        )


def test_routing_demands_use_matrix_source_to_destination_direction() -> None:
    """Test routing demands follow matrix source-to-row direction."""
    with _project("route_tile") as tile_dir:
        matrix = tile_dir / "route_tile_switch_matrix.list"
        matrix.write_text(
            "N_ROW0,N_SRC0\nE_ROW0,N_SRC0\n",
            encoding="utf-8",
        )
        tile_csv = _write_tile_csv(tile_dir, "route_tile", matrix.name)
        fab = _FakeFab(
            _FakeTile(
                "route_tile",
                tile_csv,
                matrix,
                ports=_routing_ports(),
                bels=[],
            )
        )
        data = load_matrix_data(
            RoutingDemandEvaluatorOptions(tile_name="route_tile"),
            fab,  # type: ignore[arg-type]
        )
        graph = build_graph(data)

        straight = routing.straight_routing(data, graph, limit=8, offset=0)
        turn = routing.turn_routing(data, graph, limit=8, offset=0)
        straight_actual = [(demand.source, demand.sink) for demand in straight]
        turn_actual = [(demand.source, demand.sink) for demand in turn]

        assert straight_actual == [("N_SRC0", "N_ROW0")], straight_actual
        assert turn_actual == [("N_SRC0", "E_ROW0")], turn_actual


def test_added_single_tile_demand_classes() -> None:
    """Test added single-tile demand classes generate expected probes."""
    with _project("complete_tile") as tile_dir:
        bel = Bel(
            src=_simple_bel(tile_dir).src,
            prefix="L",
            module_name="complete",
            internal=[
                ("I0", IO.INPUT),
                ("I1", IO.INPUT),
                ("RST", IO.INPUT),
                ("O", IO.OUTPUT),
            ],
            external=[],
            configPort=[],
            sharedPort=[],
            configBit=0,
            belMap={},
            userCLK=False,
            ports_vectors={},
            carry={},
            localShared={"RESET": ("RST", IO.INPUT)},
        )
        matrix = tile_dir / "complete_tile_switch_matrix.list"
        matrix.write_text(
            "\n".join(
                [
                    "J0_BEG0,A0",
                    "I0,J0_END0",
                    "I0,O",
                    "{2}I1,[O|A0]",
                    "ROUTE_A,A0",
                    "ROUTE_B,A0",
                    "ROUTE_C,ROUTE_A",
                    "RST,A0",
                    "OUT0,O",
                ]
            )
            + "\n",
            encoding="utf-8",
        )
        tile_csv = _write_tile_csv(
            tile_dir,
            "complete_tile",
            matrix.name,
            extra_rows=["JUMP,J0_BEG,0,0,J0_END,1,"],
        )
        fab = _FakeFab(
            _FakeTile(
                "complete_tile",
                tile_csv,
                matrix,
                ports=_simple_ports(),
                bels=[bel],
            )
        )
        data = load_matrix_data(
            RoutingDemandEvaluatorOptions(
                tile_name="complete_tile",
                fanout_targets=[2],
            ),
            fab,  # type: ignore[arg-type]
        )
        graph = build_graph(data)

        rows = routing.matrix_row_coverage(data, graph, limit=16, offset=0)
        sources = routing.matrix_source_usefulness(data, graph, limit=16, offset=0)
        hierarchy = routing.hierarchy_integrity(data, graph, limit=16, offset=0)
        redundancy = routing.routing_redundancy(data, graph, limit=16, offset=0)
        source_coverage = access.bel_input_source_coverage(
            data,
            graph,
            limit=16,
            offset=0,
        )
        input_fanout = fanout.bel_input_fanout(
            RoutingDemandEvaluatorOptions(
                tile_name="complete_tile",
                fanout_targets=[2],
            ),
            data,
            graph,
            limit=16,
            offset=0,
        )
        controls = fanout.control_reachability(data, graph, limit=16, offset=0)

        assert {demand.sink for demand in rows} >= {"J0_BEG0", "I0", "RST"}
        assert {demand.source for demand in sources} >= {"A0", "O"}
        assert [(demand.source, demand.sink) for demand in hierarchy] == [
            ("J0_BEG0", "J0_END0")
        ]
        assert [(demand.source, demand.sink) for demand in redundancy]
        assert ("A0", "I0") in [
            (demand.source, demand.sink) for demand in source_coverage
        ]
        assert ("O", "I1") in [
            (demand.source, demand.sink) for demand in source_coverage
        ]
        assert input_fanout[0].sinks == ["I0", "I1"]
        assert [(demand.source, demand.sink) for demand in controls] == [("A0", "RST")]


def test_matrix_diversity_demand_classes_probe_direct_choices() -> None:
    """Test fanin and source-fanout diversity generate direct choice probes."""
    with _project("diversity_tile") as tile_dir:
        matrix = tile_dir / "diversity_tile_switch_matrix.list"
        matrix.write_text(
            "\n".join(
                [
                    "{3}ROW_A,[SRC0|SRC1|SRC2]",
                    "ROW_B,SRC0",
                    "ROW_C,SRC0",
                    "ROW_D,SRC1",
                ]
            )
            + "\n",
            encoding="utf-8",
        )
        tile_csv = _write_tile_csv(tile_dir, "diversity_tile", matrix.name)
        fab = _FakeFab(_FakeTile("diversity_tile", tile_csv, matrix))
        data = load_matrix_data(
            RoutingDemandEvaluatorOptions(tile_name="diversity_tile"),
            fab,  # type: ignore[arg-type]
        )
        graph = build_graph(data)

        fanin = routing.fanin_diversity(data, graph, limit=16, offset=0)
        fanout_diversity = routing.source_fanout_diversity(
            data,
            graph,
            limit=16,
            offset=0,
        )

        assert {demand.demand_class for demand in fanin} == {
            DemandClassName.FANIN_DIVERSITY
        }
        assert {demand.kind for demand in fanin} == {DemandKind.SOFT}
        assert [(demand.source, demand.sink) for demand in fanin] == [
            ("SRC0", "ROW_A"),
            ("SRC1", "ROW_A"),
            ("SRC2", "ROW_A"),
        ]
        assert {demand.demand_class for demand in fanout_diversity} == {
            DemandClassName.SOURCE_FANOUT_DIVERSITY
        }
        assert {demand.kind for demand in fanout_diversity} == {DemandKind.SOFT}
        assert [(demand.source, demand.sink) for demand in fanout_diversity] == [
            ("SRC0", "ROW_A"),
            ("SRC0", "ROW_B"),
            ("SRC0", "ROW_C"),
            ("SRC1", "ROW_A"),
            ("SRC1", "ROW_D"),
        ]


def test_side_pair_balance_generates_ordered_side_pairs() -> None:
    """Test side-pair balance emits one probe for each ordered side pair."""
    with _project("side_pair_tile") as tile_dir:
        matrix = tile_dir / "side_pair_tile_switch_matrix.list"
        matrix.write_text(
            "\n".join(
                [
                    "{3}N_ROW0,[E_SRC0|S_SRC0|W_SRC0]",
                    "{3}E_ROW0,[N_SRC0|S_SRC0|W_SRC0]",
                    "{3}S_ROW0,[N_SRC0|E_SRC0|W_SRC0]",
                    "{3}W_ROW0,[N_SRC0|E_SRC0|S_SRC0]",
                ]
            )
            + "\n",
            encoding="utf-8",
        )
        tile_csv = _write_tile_csv(tile_dir, "side_pair_tile", matrix.name)
        fab = _FakeFab(
            _FakeTile(
                "side_pair_tile",
                tile_csv,
                matrix,
                ports=_cardinal_routing_ports(),
                bels=[],
            )
        )
        data = load_matrix_data(
            RoutingDemandEvaluatorOptions(tile_name="side_pair_tile"),
            fab,  # type: ignore[arg-type]
        )
        graph = build_graph(data)

        demands = routing.side_pair_balance(data, graph, limit=16, offset=0)

        assert {demand.demand_class for demand in demands} == {
            DemandClassName.SIDE_PAIR_BALANCE
        }
        assert {demand.kind for demand in demands} == {DemandKind.SOFT}
        assert [(demand.source, demand.sink) for demand in demands] == [
            ("N_SRC0", "E_ROW0"),
            ("N_SRC0", "S_ROW0"),
            ("N_SRC0", "W_ROW0"),
            ("E_SRC0", "N_ROW0"),
            ("E_SRC0", "S_ROW0"),
            ("E_SRC0", "W_ROW0"),
            ("S_SRC0", "N_ROW0"),
            ("S_SRC0", "E_ROW0"),
            ("S_SRC0", "W_ROW0"),
            ("W_SRC0", "N_ROW0"),
            ("W_SRC0", "E_ROW0"),
            ("W_SRC0", "S_ROW0"),
        ]


def test_routing_stress_uses_matrix_source_to_row_direction() -> None:
    """Test short/long and multi-hop demands follow matrix edge direction."""
    with _project("stress_tile") as tile_dir:
        matrix = tile_dir / "stress_tile_switch_matrix.list"
        matrix.write_text(
            "\n".join(
                [
                    "N4BEG0,N1END0",
                    "N1BEG0,N4END0",
                    "J0_BEG0,E1END0",
                    "E4BEG0,J0_END0",
                ]
            )
            + "\n",
            encoding="utf-8",
        )
        tile_csv = _write_tile_csv(
            tile_dir,
            "stress_tile",
            matrix.name,
            extra_rows=["JUMP,J0_BEG,0,0,J0_END,1,"],
        )
        fab = _FakeFab(
            _FakeTile(
                "stress_tile",
                tile_csv,
                matrix,
                ports=_short_long_ports(),
                bels=[],
            )
        )
        data = load_matrix_data(
            RoutingDemandEvaluatorOptions(tile_name="stress_tile"),
            fab,  # type: ignore[arg-type]
        )
        graph = build_graph(data)

        short_long = routing.short_to_long(data, graph, limit=8, offset=0)
        long_short = routing.long_to_short(data, graph, limit=8, offset=0)
        multi = routing.multi_hop(data, graph, limit=8, offset=0)

        assert ("N1END0", "N4BEG0") in [
            (demand.source, demand.sink) for demand in short_long
        ]
        assert ("N4END0", "N1BEG0") in [
            (demand.source, demand.sink) for demand in long_short
        ]
        assert ("E1END0", "E4BEG0") in [
            (demand.source, demand.sink) for demand in multi
        ]


def test_control_net_prefers_reachable_control_sources() -> None:
    """Test control-net demands are not dominated by unreachable sources."""
    with _project("control_tile") as tile_dir:
        bel = Bel(
            src=tile_dir / "control.v",
            prefix="L",
            module_name="control",
            internal=[
                ("RST0", IO.INPUT),
                ("EN0", IO.INPUT),
                ("O", IO.OUTPUT),
            ],
            external=[],
            configPort=[],
            sharedPort=[],
            configBit=0,
            belMap={},
            userCLK=False,
            ports_vectors={},
            carry={},
            localShared={
                "RESET": ("RST0", IO.INPUT),
                "ENABLE": ("EN0", IO.INPUT),
            },
        )
        matrix = tile_dir / "control_tile_switch_matrix.list"
        matrix.write_text(
            "\n".join(
                [
                    "RST0,VCC0",
                    "EN0,VCC0",
                    "DEAD,DEAD_SRC0",
                ]
            )
            + "\n",
            encoding="utf-8",
        )
        tile_csv = _write_tile_csv(tile_dir, "control_tile", matrix.name)
        fab = _FakeFab(
            _FakeTile(
                "control_tile",
                tile_csv,
                matrix,
                ports=[*_coverage_ports(), *_constant_ports()],
                bels=[bel],
            )
        )
        data = load_matrix_data(
            RoutingDemandEvaluatorOptions(
                tile_name="control_tile",
                fanout_targets=[2],
            ),
            fab,  # type: ignore[arg-type]
        )
        graph = build_graph(data)

        demands = fanout.control_net(
            RoutingDemandEvaluatorOptions(
                tile_name="control_tile",
                fanout_targets=[2],
            ),
            data,
            graph,
            limit=4,
            offset=0,
        )

        assert demands[0].source == "VCC0"
        assert demands[0].sinks == ["RST0", "EN0"]


def test_bel_input_source_coverage_is_not_first_source_biased() -> None:
    """Test BEL-input source coverage spreads probes across sources."""
    with _project("coverage_tile") as tile_dir:
        bel = Bel(
            src=tile_dir / "coverage.v",
            prefix="L",
            module_name="coverage",
            internal=[
                ("I0", IO.INPUT),
                ("I1", IO.INPUT),
                ("I2", IO.INPUT),
                ("O", IO.OUTPUT),
            ],
            external=[],
            configPort=[],
            sharedPort=[],
            configBit=0,
            belMap={},
            userCLK=False,
            ports_vectors={},
            carry={},
            localShared={},
        )
        matrix = tile_dir / "coverage_tile_switch_matrix.list"
        matrix.write_text(
            "\n".join(
                [
                    "DEAD,DEAD_SRC0",
                    "I0,GOOD_SRC0",
                    "I1,GOOD_SRC0",
                    "I2,GOOD_SRC0",
                    "I0,O",
                    "I1,O",
                    "I2,O",
                ]
            )
            + "\n",
            encoding="utf-8",
        )
        tile_csv = _write_tile_csv(tile_dir, "coverage_tile", matrix.name)
        fab = _FakeFab(
            _FakeTile(
                "coverage_tile",
                tile_csv,
                matrix,
                ports=_coverage_ports(),
                bels=[bel],
            )
        )
        data = load_matrix_data(
            RoutingDemandEvaluatorOptions(tile_name="coverage_tile"),
            fab,  # type: ignore[arg-type]
        )
        graph = build_graph(data)

        demands = access.bel_input_source_coverage(data, graph, limit=4, offset=0)
        pairs = [(demand.source, demand.sink) for demand in demands]

        assert ("GOOD_SRC0", "I0") in pairs
        assert ("DEAD_SRC0", "I0") in pairs


def test_random_demands_sample_from_reachable_candidates() -> None:
    """Test random demands do not miss sparse reachable pairs by chance."""
    with _project("random_tile") as tile_dir:
        matrix = tile_dir / "random_tile_switch_matrix.list"
        matrix.write_text(
            "\n".join(
                [
                    "SINK00,SRC00",
                    *[f"DEAD{i}0,SRC{i + 1}0" for i in range(40)],
                ]
            )
            + "\n",
            encoding="utf-8",
        )
        tile_csv = _write_tile_csv(tile_dir, "random_tile", matrix.name)
        fab = _FakeFab(
            _FakeTile(
                "random_tile",
                tile_csv,
                matrix,
                ports=_many_local_ports(41),
                bels=[],
            )
        )
        data = load_matrix_data(
            RoutingDemandEvaluatorOptions(tile_name="random_tile"),
            fab,  # type: ignore[arg-type]
        )
        graph = build_graph(data)

        demands = random.random_terminal_pairs(
            demand_class="random_local",
            matrix=data,
            graph=graph,
            rng=Random(1),
            limit=4,
            offset=0,
            distance="local",
        )

        assert [(demand.source, demand.sink) for demand in demands] == [
            ("SRC00", "SINK00")
        ]


def test_evaluator_runs_added_profiles() -> None:
    """Test added public profiles execute through the evaluator."""
    with _project("profile_tile") as tile_dir:
        matrix = tile_dir / "profile_tile_switch_matrix.list"
        matrix.write_text("I,A0\nI,O\nOUT0,O\nOUT0,A0\n", encoding="utf-8")
        tile_csv = _write_tile_csv(tile_dir, "profile_tile", matrix.name)
        fab = _FakeFab(
            _FakeTile(
                "profile_tile",
                tile_csv,
                matrix,
                ports=_simple_ports(),
                bels=[_simple_bel(tile_dir)],
            )
        )

        for profile in [
            DemandProfileName.ROUTING_STRESS,
            DemandProfileName.CONTROL_STRESS,
            DemandProfileName.FULL,
        ]:
            result = RoutingDemandEvaluator(
                RoutingDemandEvaluatorOptions(
                    tile_name="profile_tile",
                    demand_profile=profile,
                    demand_iterations=16,
                    track_progress=False,
                )
            ).run(object(), fab)  # type: ignore[arg-type]

            assert result.demand_profile.profile_name == profile
            assert result.stats.total_demands >= 0


def test_evaluator_reports_unreachable_random_soft_demands() -> None:
    """Test soft random demands can fail without failing hard demands."""
    with _project("soft_tile") as tile_dir:
        matrix = tile_dir / "soft_tile_switch_matrix.list"
        matrix.write_text("I,A0\nI,O\nOUT0,O\nOUT0,A0\n", encoding="utf-8")
        tile_csv = _write_tile_csv(tile_dir, "soft_tile", matrix.name)
        fab = _FakeFab(
            _FakeTile(
                "soft_tile",
                tile_csv,
                matrix,
                ports=_simple_ports(),
                bels=[_simple_bel(tile_dir)],
            )
        )

        result = RoutingDemandEvaluator(
            RoutingDemandEvaluatorOptions(
                tile_name="soft_tile",
                demand_profile="default",
                demand_iterations=12,
                random_demand_ratio=0.75,
                seed=3,
                track_progress=False,
            )
        ).run(object(), fab)  # type: ignore[arg-type]

        assert result.stats.hard_failed == 0
        assert result.stats.total_demands >= 2


def test_greedy_optimizer_prunes_redundant_pips_without_writeback() -> None:
    """Test greedy optimizer removes redundant PIPs in report-only mode."""
    with _project("opt_tile") as tile_dir:
        matrix = tile_dir / "opt_tile_switch_matrix.list"
        original_matrix = "{2}I,[A0|DEAD]\nOUT0,O\n"
        matrix.write_text(original_matrix, encoding="utf-8")
        tile_csv = _write_tile_csv(tile_dir, "opt_tile", matrix.name)
        fab = _FakeFab(
            _FakeTile(
                "opt_tile",
                tile_csv,
                matrix,
                ports=_simple_ports(),
                bels=[_simple_bel(tile_dir)],
            )
        )

        result = RoutingDemandEvaluator(
            RoutingDemandEvaluatorOptions(
                tile_name="opt_tile",
                demand_profile="minimal",
                demand_iterations=4,
                opt=True,
                optimizer="greedy",
                opt_target_pip_reduction=0.25,
                opt_max_hard_failure_rate=0.0,
                opt_max_soft_failure_rate=0.0,
                opt_use_baseline_failure_rates=True,
                opt_write_back=False,
                opt_max_iterations=8,
                track_progress=False,
            )
        ).run(object(), fab)  # type: ignore[arg-type]

        assert result.optimizer_stats is not None
        assert result.optimizer_stats.accepted_pips == 1
        assert result.optimizer_stats.removed_pips == 1
        assert result.optimizer_stats.mux_cleanup.rows_crossing_thresholds == 1
        assert result.optimizer_stats.mux_cleanup.direct_wire_conversions == 1
        assert result.optimizer_stats.mux_cleanup.config_bit_reduction == 1
        assert result.stats.final_pips < result.stats.original_pips
        assert result.stats.hard_failed == 0
        assert "## Optimization" in result.report_summary
        assert "## Mux Cleanup" in result.report_summary
        assert "### Mux Buckets" in result.report_summary
        assert "### Rows Crossing Mux Thresholds" in result.report_summary
        assert matrix.read_text(encoding="utf-8") == original_matrix


def test_greedy_writeback_list_renderer_keeps_fabulous_list_valid() -> None:
    """Test greedy write-back never emits invalid zero-connection list rows."""
    with _project("writeback_zero") as tile_dir:
        matrix = tile_dir / "writeback_zero_switch_matrix.list"
        rendered = _render_list(
            "writeback_zero",
            {
                "I": ["A0"],
                "JS2BEG7": [],
            },
        )
        matrix.write_text(rendered, encoding="utf-8")

        pairs = parseList(matrix)

        assert "{0}" not in rendered
        assert pairs == [("I", "A0")]


def test_greedy_batch_filter_preserves_one_pip_per_matrix_row() -> None:
    """Test greedy batches cannot remove the last PIP from any row."""
    removable = _remove_emptying_pips(
        {
            "A": ["S0", "S1", "S2"],
            "B": ["S3"],
        },
        [
            ("S0", "A"),
            ("S1", "A"),
            ("S2", "A"),
            ("S3", "B"),
        ],
    )

    assert removable == [("S0", "A"), ("S1", "A")]


def test_greedy_power_of_two_mux_cleanup_normalizes_rows() -> None:
    """Test power-of-two mux cleanup targets non-power-of-two rows."""
    with _project("power_mux") as tile_dir:
        matrix = tile_dir / "power_mux_switch_matrix.list"
        matrix.write_text("{3}I,[A0|A1|DEAD]\nOUT0,O\n", encoding="utf-8")
        tile_csv = _write_tile_csv(tile_dir, "power_mux", matrix.name)
        fab = _FakeFab(
            _FakeTile(
                "power_mux",
                tile_csv,
                matrix,
                ports=_simple_ports(),
                bels=[_simple_bel(tile_dir)],
            )
        )

        result = RoutingDemandEvaluator(
            RoutingDemandEvaluatorOptions(
                tile_name="power_mux",
                demand_profile="minimal",
                demand_iterations=4,
                opt=True,
                optimizer="greedy",
                opt_target_pip_reduction=0.25,
                opt_max_hard_failure_rate=0.0,
                opt_max_soft_failure_rate=0.0,
                opt_power_of_two_muxes=True,
                opt_write_back=False,
                opt_max_iterations=4,
                track_progress=False,
            )
        ).run(object(), fab)  # type: ignore[arg-type]

        assert result.options.opt_clean_mux is True
        assert result.optimizer_stats is not None
        assert result.optimizer_stats.accepted_pips == 1
        assert result.optimizer_stats.mux_cleanup.rows_crossing_thresholds == 1
        changed = result.optimizer_stats.mux_cleanup.changed_rows[0]
        assert changed.row == "I"
        assert changed.fanin_before == 3
        assert changed.fanin_after == 2
        assert changed.bucket_before == "mux4"
        assert changed.bucket_after == "mux2"
        assert "power-of-two mux cleanup" in result.report_summary
        assert matrix.read_text(encoding="utf-8") == "{3}I,[A0|A1|DEAD]\nOUT0,O\n"


def test_greedy_clean_mux_writeback_allows_non_power_rows() -> None:
    """Test non-strict greedy mux cleanup can write non-power mux rows."""
    with _project("clean_mux_non_power") as tile_dir:
        matrix = tile_dir / "clean_mux_non_power_switch_matrix.list"
        original_matrix = "{3}I,[A0|A1|DEAD]\n{8}X,[X0|X1|X2|X3|X4|X5|X6|X7]\nOUT0,O\n"
        matrix.write_text(original_matrix, encoding="utf-8")
        tile_csv = _write_tile_csv(tile_dir, "clean_mux_non_power", matrix.name)
        fab = _FakeFab(
            _FakeTile(
                "clean_mux_non_power",
                tile_csv,
                matrix,
                ports=_simple_ports(),
                bels=[_simple_bel(tile_dir)],
            )
        )

        result = RoutingDemandEvaluator(
            RoutingDemandEvaluatorOptions(
                tile_name="clean_mux_non_power",
                demand_profile="minimal",
                demand_iterations=4,
                opt=True,
                optimizer="greedy",
                opt_target_pip_reduction=0.01,
                opt_max_hard_failure_rate=1.0,
                opt_max_soft_failure_rate=1.0,
                opt_clean_mux=True,
                opt_power_of_two_muxes=False,
                opt_write_back=True,
                opt_max_iterations=4,
                track_progress=False,
            )
        ).run(object(), fab)  # type: ignore[arg-type]

        assert result.optimizer_stats is not None
        assert result.optimizer_stats.write_back is True
        assert result.optimizer_stats.accepted_pips == 4
        assert result.optimizer_stats.mux_cleanup.non_power_of_two_mux_rows_after == 1
        assert "Write-back skipped because strict power-of-two mux cleanup" not in (
            result.report_summary
        )
        written = matrix.read_text(encoding="utf-8")
        assert "{3}I,[A0|A1|DEAD]" in written
        assert "{4}X," in written


def test_greedy_power_of_two_mux_cleanup_does_not_overshoot_budget() -> None:
    """Test strict power-of-two mux cleanup treats the target as a budget."""
    with _project("power_mux_budget") as tile_dir:
        matrix = tile_dir / "power_mux_budget_switch_matrix.list"
        original_matrix = "{6}I,[A0|A1|A2|A3|A4|DEAD]\nOUT0,O\n"
        matrix.write_text(original_matrix, encoding="utf-8")
        tile_csv = _write_tile_csv(tile_dir, "power_mux_budget", matrix.name)
        fab = _FakeFab(
            _FakeTile(
                "power_mux_budget",
                tile_csv,
                matrix,
                ports=_simple_ports(),
                bels=[_simple_bel(tile_dir)],
            )
        )

        result = RoutingDemandEvaluator(
            RoutingDemandEvaluatorOptions(
                tile_name="power_mux_budget",
                demand_profile="minimal",
                demand_iterations=4,
                opt=True,
                optimizer="greedy",
                opt_target_pip_reduction=0.1,
                opt_max_hard_failure_rate=0.0,
                opt_max_soft_failure_rate=0.0,
                opt_power_of_two_muxes=True,
                opt_write_back=False,
                opt_max_iterations=4,
                track_progress=False,
            )
        ).run(object(), fab)  # type: ignore[arg-type]

        assert result.optimizer_stats is not None
        assert result.optimizer_stats.accepted_pips == 0
        assert result.optimizer_stats.stop_reason == "power_of_two_budget_exhausted"
        assert result.optimizer_stats.mux_cleanup.non_power_of_two_mux_rows_after == 1
        assert "Write-back skipped because strict power-of-two mux cleanup" in (
            result.report_summary
        )
        assert matrix.read_text(encoding="utf-8") == original_matrix


def test_monte_carlo_optimizer_prunes_and_reports_importance() -> None:
    """Test Monte Carlo optimizer prunes and reports PIP importance."""
    with _project("monte_tile") as tile_dir:
        matrix = tile_dir / "monte_tile_switch_matrix.list"
        original_matrix = "{2}I,[A0|DEAD]\nOUT0,O\n"
        matrix.write_text(original_matrix, encoding="utf-8")
        tile_csv = _write_tile_csv(tile_dir, "monte_tile", matrix.name)
        fab = _FakeFab(
            _FakeTile(
                "monte_tile",
                tile_csv,
                matrix,
                ports=_simple_ports(),
                bels=[_simple_bel(tile_dir)],
            )
        )

        result = RoutingDemandEvaluator(
            RoutingDemandEvaluatorOptions(
                tile_name="monte_tile",
                demand_profile="minimal",
                demand_iterations=4,
                opt=True,
                optimizer="monte_carlo",
                opt_target_pip_reduction=0.25,
                opt_max_hard_failure_rate=0.0,
                opt_max_soft_failure_rate=0.0,
                opt_use_baseline_failure_rates=True,
                opt_write_back=False,
                opt_max_iterations=20,
                track_progress=False,
            )
        ).run(object(), fab)  # type: ignore[arg-type]

        assert result.optimizer_stats is not None
        assert result.optimizer_stats.accepted_pips == 1
        assert result.optimizer_stats.removed_pips == 1
        assert result.optimizer_stats.learning_iterations == 20
        assert result.optimizer_stats.pruning_iterations >= 1
        assert result.optimizer_stats.sampled_batches >= 1
        assert result.optimizer_stats.weight_change_rate >= 0.0
        assert result.optimizer_stats.sampled_pips >= 1
        assert result.optimizer_stats.sampled_pip_rate > 0.0
        assert result.optimizer_stats.pip_importance_matrix["I"]
        assert result.optimizer_stats.pip_importance_file is None
        assert "## PIP Importance" in result.report_summary
        assert matrix.read_text(encoding="utf-8") == original_matrix


def test_pnr_pass_wrapper_exposes_result_data() -> None:
    """Test PnR pass wrapper stores result data and report text."""
    with _project("pass_tile") as tile_dir:
        matrix = tile_dir / "pass_tile_switch_matrix.list"
        matrix.write_text("I,A0\nI,O\nOUT0,O\n", encoding="utf-8")
        tile_csv = _write_tile_csv(tile_dir, "pass_tile", matrix.name)
        fab = _FakeFab(
            _FakeTile(
                "pass_tile",
                tile_csv,
                matrix,
                ports=_simple_ports(),
                bels=[_simple_bel(tile_dir)],
            )
        )
        pass_ = RoutingDemandEvaluatorPass(
            tile_name="pass_tile",
            demand_profile="minimal",
            demand_iterations=2,
            track_progress=False,
        )

        pass_.run_on(object(), fab)  # type: ignore[arg-type]

        assert pass_.result_data is not None
        assert "Routing Demand Evaluator Report" in pass_.report_summary


def _project(tile_name: str) -> object:
    """Create a temporary tile directory context.

    Parameters
    ----------
    tile_name : str
        Tile name.

    Returns
    -------
    object
        Temporary directory context.
    """
    return _ProjectContext(tile_name)


class _ProjectContext:
    """Temporary project context for routing-demand tests.

    Parameters
    ----------
    tile_name : str
        Tile name.
    """

    def __init__(self, tile_name: str) -> None:
        self.tile_name = tile_name
        self._tmp: TemporaryDirectory[str] | None = None

    def __enter__(self) -> Path:
        """Create and return a tile directory.

        Returns
        -------
        Path
            Tile directory.
        """
        self._tmp = TemporaryDirectory(prefix="routing_demand_evaluator_")
        root = Path(self._tmp.name)
        tile_dir = root / "Tile" / self.tile_name
        tile_dir.mkdir(parents=True)
        return tile_dir

    def __exit__(self, *args: object) -> None:
        """Clean up the temporary directory.

        Parameters
        ----------
        *args : object
            Context-manager exception information.
        """
        assert self._tmp is not None
        self._tmp.cleanup()


def _write_tile_csv(
    tile_dir: Path,
    tile_name: str,
    matrix_name: str,
    extra_rows: list[str] | None = None,
) -> Path:
    """Write a small tile CSV.

    Parameters
    ----------
    tile_dir : Path
        Tile directory.
    tile_name : str
        Tile name.
    matrix_name : str
        Matrix file name.
    extra_rows : list[str] | None
        Extra tile rows.

    Returns
    -------
    Path
        Tile CSV path.
    """
    rows = [
        f"TILE,{tile_name}",
        *(extra_rows or []),
        f"MATRIX,./{matrix_name}",
        "EndTILE",
    ]
    tile_csv = tile_dir / f"{tile_name}.csv"
    tile_csv.write_text("\n".join(rows) + "\n", encoding="utf-8")
    return tile_csv


def _simple_ports() -> list[Port]:
    """Return one simple routing port pair.

    Returns
    -------
    list[Port]
        FABulous ports for source ``A`` and destination ``OUT``.
    """
    ports, _common = parsePortLine("NORTH,A,0,1,OUT,1,")
    return ports


def _escape_ports() -> list[Port]:
    """Return ports that expose the matrix-side escape bug.

    Returns
    -------
    list[Port]
        FABulous ports whose sink-side terminal is not the BEL escape row.
    """
    ports, _common = parsePortLine("NORTH,N1BEG,0,1,N1END,1,")
    return ports


def _routing_ports() -> list[Port]:
    """Return ports for routing source-to-destination direction tests.

    Returns
    -------
    list[Port]
        FABulous ports for north and east routing resources.
    """
    north_ports, _common = parsePortLine("NORTH,N_ROW,0,1,N_SRC,1,")
    east_ports, _common = parsePortLine("EAST,E_ROW,1,0,E_SRC,1,")
    return [*north_ports, *east_ports]


def _cardinal_routing_ports() -> list[Port]:
    """Return one source/row port pair per cardinal direction.

    Returns
    -------
    list[Port]
        FABulous ports for north, east, south, and west routing resources.
    """
    north_ports, _common = parsePortLine("NORTH,N_ROW,0,1,N_SRC,1,")
    east_ports, _common = parsePortLine("EAST,E_ROW,1,0,E_SRC,1,")
    south_ports, _common = parsePortLine("SOUTH,S_ROW,0,-1,S_SRC,1,")
    west_ports, _common = parsePortLine("WEST,W_ROW,-1,0,W_SRC,1,")
    return [*north_ports, *east_ports, *south_ports, *west_ports]


def _short_long_ports() -> list[Port]:
    """Return routing ports with short and long spans.

    Returns
    -------
    list[Port]
        FABulous ports for short/long routing stress tests.
    """
    north_short, _common = parsePortLine("NORTH,N1BEG,0,-1,N1END,1,")
    north_long, _common = parsePortLine("NORTH,N4BEG,0,-4,N4END,1,")
    east_short, _common = parsePortLine("EAST,E1BEG,1,0,E1END,1,")
    east_long, _common = parsePortLine("EAST,E4BEG,4,0,E4END,1,")
    return [*north_short, *north_long, *east_short, *east_long]


def _coverage_ports() -> list[Port]:
    """Return ports for source-coverage bias tests.

    Returns
    -------
    list[Port]
        FABulous ports for one dead source and one useful source.
    """
    dead_ports, _common = parsePortLine("NORTH,DEAD_SRC,0,1,DEAD,1,")
    good_ports, _common = parsePortLine("EAST,GOOD_SRC,1,0,GOOD,1,")
    return [*dead_ports, *good_ports]


def _constant_ports() -> list[Port]:
    """Return FABulous constant pseudo-wire ports.

    Returns
    -------
    list[Port]
        Constant source ports.
    """
    vcc_ports, _common = parsePortLine("JUMP,NULL,0,0,VCC,1,")
    return vcc_ports


def _many_local_ports(count: int) -> list[Port]:
    """Return many local routing port pairs.

    Parameters
    ----------
    count : int
        Number of one-wire port pairs.

    Returns
    -------
    list[Port]
        FABulous ports for generated local pairs.
    """
    ports: list[Port] = []
    for index in range(count):
        parsed, _common = parsePortLine(f"NORTH,SRC{index},0,1,SINK{index},1,")
        ports.extend(parsed)
    return ports


def _carry_ports() -> list[Port]:
    """Return carry-annotated tile ports.

    Returns
    -------
    list[Port]
        FABulous ports for carry input and output resources.
    """
    ports, _common = parsePortLine('NORTH,Co,0,-1,Ci,1,CARRY="C0"')
    return ports


def _simple_bel(tile_dir: Path) -> Bel:
    """Return one simple BEL.

    Parameters
    ----------
    tile_dir : Path
        Temporary tile directory.

    Returns
    -------
    Bel
        Simple BEL with one input and one output.
    """
    return Bel(
        src=tile_dir / "simple.v",
        prefix="",
        module_name="simple",
        internal=[("I", IO.INPUT), ("O", IO.OUTPUT)],
        external=[],
        configPort=[],
        sharedPort=[],
        configBit=0,
        belMap={},
        userCLK=False,
        ports_vectors={},
        carry={},
        localShared={},
    )


def _feature_bel(tile_dir: Path) -> Bel:
    """Return one BEL with carry and local shared features.

    Parameters
    ----------
    tile_dir : Path
        Temporary tile directory.

    Returns
    -------
    Bel
        Feature-rich test BEL.
    """
    return Bel(
        src=tile_dir / "feature.v",
        prefix="",
        module_name="feature",
        internal=[
            ("I", IO.INPUT),
            ("O", IO.OUTPUT),
            ("Ci", IO.INPUT),
            ("Co", IO.OUTPUT),
            ("RST", IO.INPUT),
            ("EN", IO.INPUT),
        ],
        external=[],
        configPort=[],
        sharedPort=[],
        configBit=0,
        belMap={},
        userCLK=False,
        ports_vectors={},
        carry={"C": {IO.INPUT: "Ci", IO.OUTPUT: "Co"}},
        localShared={
            "RESET": ("RST", IO.INPUT),
            "ENABLE": ("EN", IO.INPUT),
        },
    )


def _assert_raises_contains(fn: object, expected: str) -> None:
    """Assert a callable raises an exception containing text.

    Parameters
    ----------
    fn : object
        Callable expected to raise.
    expected : str
        Expected exception text.

    Raises
    ------
    AssertionError
        If the callable does not raise or the message does not match.
    """
    try:
        fn()
    except Exception as exc:
        if expected not in str(exc):
            raise AssertionError(f"expected {expected!r} in {exc!s}") from exc
        return
    raise AssertionError("expected callable to raise")


def main() -> None:
    """Run all routing-demand evaluator tests."""
    test_models_validate_public_options()
    test_matrix_loader_reads_list_and_jump_edges()
    test_matrix_loader_skips_source_less_jump_resources()
    test_matrix_loader_classifies_fabulous_terminals()
    test_matrix_loader_classifies_tile_carry_ports_from_csv()
    test_carry_chain_uses_actual_matrix_carry_segments()
    test_hierarchy_fed_single_fanin_bel_input_counts_as_generic()
    test_pathfinder_routes_through_jump_edge()
    test_pathfinder_routes_multi_sink_net()
    test_evaluator_runs_minimal_profile()
    test_bel_output_escape_uses_matrix_destination_rows()
    test_routing_demands_use_matrix_source_to_destination_direction()
    test_added_single_tile_demand_classes()
    test_matrix_diversity_demand_classes_probe_direct_choices()
    test_side_pair_balance_generates_ordered_side_pairs()
    test_routing_stress_uses_matrix_source_to_row_direction()
    test_control_net_prefers_reachable_control_sources()
    test_bel_input_source_coverage_is_not_first_source_biased()
    test_random_demands_sample_from_reachable_candidates()
    test_evaluator_runs_added_profiles()
    test_evaluator_reports_unreachable_random_soft_demands()
    test_greedy_optimizer_prunes_redundant_pips_without_writeback()
    test_greedy_writeback_list_renderer_keeps_fabulous_list_valid()
    test_greedy_batch_filter_preserves_one_pip_per_matrix_row()
    test_greedy_power_of_two_mux_cleanup_normalizes_rows()
    test_greedy_clean_mux_writeback_allows_non_power_rows()
    test_greedy_power_of_two_mux_cleanup_does_not_overshoot_budget()
    test_monte_carlo_optimizer_prunes_and_reports_importance()
    test_pnr_pass_wrapper_exposes_result_data()


if __name__ == "__main__":
    main()
