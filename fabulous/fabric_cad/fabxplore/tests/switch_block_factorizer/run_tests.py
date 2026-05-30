"""Tests for the graph-local switch-block factorizer module."""

from __future__ import annotations

from fabulous.fabric_cad.fabxplore.modules.switch_block_factorizer import (
    MuxReductionRule,
    SwitchBlockFactorizer,
    SwitchBlockFactorizerOptions,
)
from fabulous.fabric_cad.fabxplore.pnr.custom_passes import (
    SwitchBlockFactorizerPass,
)
from fabulous.fabric_cad.fabxplore.pnr.fab_graph.core.models import (
    RoutingConfigBits,
    RoutingSwitchMatrix,
)
from fabulous.fabric_definition.define import Direction

Connections = dict[str, list[str]]


def test_factorizer_updates_graph_without_writing_files() -> None:
    """Factorize an active graph matrix with one coarse graph write."""
    graph = _FakePnRBridge(
        {
            "LA_I0": ["N0", "N1", "E0", "E1", "S0", "S1", "W0", "W1"],
            "KEEP": ["X0"],
        }
    )

    result = SwitchBlockFactorizer(
        SwitchBlockFactorizerOptions(
            tile_name="fac_tile",
            global_reduction=1,
            track_progress=False,
        )
    ).run(graph)

    assert graph.set_switch_matrix_calls == 1
    assert graph.writes_called == 0
    assert graph.connections["J_FAC_G0_0_BEG0"] == ["N0", "N1", "E0", "E1"]
    assert graph.connections["J_FAC_G0_1_BEG0"] == ["S0", "S1", "W0", "W1"]
    assert graph.connections["LA_I0"] == [
        "J_FAC_G0_0_END0",
        "J_FAC_G0_1_END0",
    ]
    assert graph.connections["KEEP"] == ["X0"]
    assert graph.added_external_resources == [
        ("J_FAC_G0_0_BEG", "J_FAC_G0_0_END"),
        ("J_FAC_G0_1_BEG", "J_FAC_G0_1_END"),
    ]
    assert result.stats.added_jump_wires == 2
    assert result.stats.max_fanin_before == 8
    assert result.stats.max_fanin_after == 4
    assert result.stats.reachability_preserved


def test_factorizer_applies_global_before_explicit_rules() -> None:
    """Apply explicit rules after graph-local global factorization."""
    graph = _FakePnRBridge({"OUT": [f"S{i}" for i in range(16)]})

    result = SwitchBlockFactorizer(
        SwitchBlockFactorizerOptions(
            tile_name="rule_tile",
            global_reduction=1,
            reduction_rules=[MuxReductionRule(from_fanin=8, to_fanin=4)],
            track_progress=False,
        )
    ).run(graph)

    assert result.stats.added_jump_wires == 6
    assert result.stats.max_fanin_after == 4
    assert graph.connections["OUT"] == [
        "J_FAC_G0_0_END0",
        "J_FAC_G0_1_END0",
    ]
    assert graph.connections["J_FAC_G0_0_BEG0"] == [
        "J_FAC_R0_2_END0",
        "J_FAC_R0_3_END0",
    ]
    assert graph.connections["J_FAC_R0_2_BEG0"] == ["S0", "S1", "S2", "S3"]


def test_factorizer_blocks_moves_over_relative_config_margin() -> None:
    """Keep the graph unchanged when a reduction exceeds the relative budget."""
    graph = _FakePnRBridge({"LA_I0": ["N0", "N1", "E0", "E1", "S0", "S1", "W0", "W1"]})

    result = SwitchBlockFactorizer(
        SwitchBlockFactorizerOptions(
            tile_name="limit_tile",
            global_reduction=1,
            config_bit_margin=0,
            track_progress=False,
        )
    ).run(graph)

    assert graph.connections == {
        "LA_I0": ["N0", "N1", "E0", "E1", "S0", "S1", "W0", "W1"]
    }
    assert graph.added_external_resources == []
    assert result.stats.effective_config_bit_limit == 3
    assert result.stats.blocked_reductions == 1
    assert result.stats.added_jump_wires == 0


def test_factorizer_uses_lower_absolute_or_relative_config_limit() -> None:
    """Use the lower configured limit when both config budgets are present."""
    graph = _FakePnRBridge(
        {"LA_I0": ["N0", "N1", "E0", "E1", "S0", "S1", "W0", "W1"]},
        fixed_config_bits=5,
    )

    result = SwitchBlockFactorizer(
        SwitchBlockFactorizerOptions(
            tile_name="budget_tile",
            global_reduction=1,
            config_bit_margin=10,
            config_bit_limit=9,
            track_progress=False,
        )
    ).run(graph)

    assert result.stats.total_config_bits_before == 8
    assert result.stats.effective_config_bit_limit == 9
    assert result.stats.total_config_bits_after == 8
    assert result.stats.blocked_reductions == 1
    assert graph.added_external_resources == []


def test_factorizer_accepts_moves_within_config_margin() -> None:
    """Apply reductions while the local config estimate fits the budget."""
    graph = _FakePnRBridge({"LA_I0": ["N0", "N1", "E0", "E1", "S0", "S1", "W0", "W1"]})

    result = SwitchBlockFactorizer(
        SwitchBlockFactorizerOptions(
            tile_name="margin_tile",
            global_reduction=1,
            config_bit_margin=3,
            track_progress=False,
        )
    ).run(graph)

    assert result.stats.effective_config_bit_limit == 6
    assert result.stats.total_config_bits_after == 5
    assert result.stats.added_jump_wires == 2


def test_factorizer_treats_max_added_jump_wires_as_graph_limit() -> None:
    """Skip reductions that would exceed the JUMP-resource budget."""
    graph = _FakePnRBridge({"LA_I0": ["N0", "N1", "E0", "E1", "S0", "S1", "W0", "W1"]})

    result = SwitchBlockFactorizer(
        SwitchBlockFactorizerOptions(
            tile_name="jump_limit_tile",
            global_reduction=1,
            max_added_jump_wires=1,
            track_progress=False,
        )
    ).run(graph)

    assert result.stats.blocked_reductions == 1
    assert result.stats.added_jump_wires == 0
    assert graph.added_external_resources == []
    assert graph.connections["LA_I0"] == [
        "N0",
        "N1",
        "E0",
        "E1",
        "S0",
        "S1",
        "W0",
        "W1",
    ]


def test_factorizer_bypasses_single_source_remainder_chunks() -> None:
    """Do not generate mux1 JUMP stages for uneven factorization chunks."""
    graph = _FakePnRBridge({"OUT": [f"S{i}" for i in range(9)]})

    result = SwitchBlockFactorizer(
        SwitchBlockFactorizerOptions(
            tile_name="uneven_tile",
            global_reduction=None,
            reduction_rules=[MuxReductionRule(from_fanin=9, to_fanin=4)],
            track_progress=False,
        )
    ).run(graph)

    assert result.stats.added_jump_wires == 2
    assert result.stats.fanin_histogram_after == {4: 2, 3: 1}
    assert graph.connections["J_FAC_R0_0_BEG0"] == ["S0", "S1", "S2", "S3"]
    assert graph.connections["J_FAC_R0_1_BEG0"] == ["S4", "S5", "S6", "S7"]
    assert set(graph.connections["OUT"]) == {
        "J_FAC_R0_0_END0",
        "J_FAC_R0_1_END0",
        "S8",
    }
    assert not any(sources == ["S8"] for sources in graph.connections.values())


def test_factorizer_pass_exposes_result_data() -> None:
    """Test PnR pass wrapper stores structured result data."""
    graph = _FakePnRBridge({"OUT": ["A", "B", "C", "D"]})
    switch_pass = SwitchBlockFactorizerPass(
        tile_name="pass_tile",
        global_reduction=1,
        track_progress=False,
    )

    switch_pass.run_on(graph)

    assert switch_pass.result_data is not None
    assert switch_pass.result_data.stats.added_jump_wires == 2
    assert "Switch Block Factorizer Report" in switch_pass.report_summary


class _FakePnRBridge:
    """Small graph-shaped factorizer test double."""

    def __init__(
        self,
        connections: Connections,
        *,
        fixed_config_bits: int = 0,
    ) -> None:
        self.tile_name = "fac_tile"
        self.connections = {row: list(sources) for row, sources in connections.items()}
        self.fixed_config_bits = fixed_config_bits
        self.added_external_resources: list[tuple[str, str]] = []
        self.set_switch_matrix_calls = 0
        self.writes_called = 0

    def switch_matrix(self, tile_name: str) -> RoutingSwitchMatrix:
        """Return the current fake graph matrix."""
        _ = tile_name
        rows = list(self.connections)
        columns = list(
            dict.fromkeys(
                source for sources in self.connections.values() for source in sources
            )
        )
        column_index = {column: index for index, column in enumerate(columns)}
        matrix = [[0.0 for _column in columns] for _row in rows]
        for row_index, row in enumerate(rows):
            for source in self.connections[row]:
                matrix[row_index][column_index[source]] = 8.0
        return RoutingSwitchMatrix(
            tile_type=tile_name,
            columns=columns,
            rows=rows,
            matrix=matrix,
        )

    def set_switch_matrix(
        self,
        tile_name: str,
        columns: list[str],
        rows: list[str],
        matrix: list[list[float]],
    ) -> None:
        """Replace the fake graph matrix."""
        _ = tile_name
        self.set_switch_matrix_calls += 1
        self.connections = {}
        for row_index, row in enumerate(rows):
            sources = [
                column
                for column_index, column in enumerate(columns)
                if matrix[row_index][column_index] > 0
            ]
            if sources:
                self.connections[row] = sources

    def add_external_resource(
        self,
        tile_name: str,
        direction: Direction,
        source_name: str,
        x_offset: int,
        y_offset: int,
        destination_name: str,
        wire_count: int,
    ) -> None:
        """Record generated JUMP resources."""
        _ = tile_name
        assert direction is Direction.JUMP
        assert (x_offset, y_offset, wire_count) == (0, 0, 1)
        self.added_external_resources.append((source_name, destination_name))

    def get_config_bits(self, tile_name: str) -> RoutingConfigBits:
        """Return config bits estimated from the current fake graph."""
        _ = tile_name
        matrix_bits = sum(
            (len(sources) - 1).bit_length()
            for sources in self.connections.values()
            if len(sources) >= 2
        )
        return RoutingConfigBits(
            tile_type=tile_name,
            matrix_config_bits=matrix_bits,
            fixed_config_bits=self.fixed_config_bits,
            total_config_bits=matrix_bits + self.fixed_config_bits,
        )

    def write_tile_sources(self, *args: object, **kwargs: object) -> None:
        """Record unexpected file writes."""
        _ = args, kwargs
        self.writes_called += 1

    def write_project(self, *args: object, **kwargs: object) -> None:
        """Record unexpected project writes."""
        _ = args, kwargs
        self.writes_called += 1

    def write_pips(self, *args: object, **kwargs: object) -> None:
        """Record unexpected pips writes."""
        _ = args, kwargs
        self.writes_called += 1


if __name__ == "__main__":
    test_factorizer_updates_graph_without_writing_files()
    test_factorizer_applies_global_before_explicit_rules()
    test_factorizer_blocks_moves_over_relative_config_margin()
    test_factorizer_uses_lower_absolute_or_relative_config_limit()
    test_factorizer_accepts_moves_within_config_margin()
    test_factorizer_treats_max_added_jump_wires_as_graph_limit()
    test_factorizer_bypasses_single_source_remainder_chunks()
    test_factorizer_pass_exposes_result_data()
