"""Tests for the FABulous FASM utility parser."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

import pytest

from fabulous.fabric_cad.fabxplore.pnr.fab_graph.core.models import (
    RoutingEndpoint,
    RoutingPip,
    RoutingPipKind,
    RoutingResourceKey,
)
from fabulous.fabric_cad.fabxplore.utils.fabulous_fasm import (
    FabulousFasmFeatureType,
    FabulousFasmResolveError,
    parse_fabulous_fasm,
)

if TYPE_CHECKING:
    from collections.abc import Callable, Iterator


def test_parse_fabulous_fasm_ignores_comments_and_parses_feature_shapes() -> None:
    """Parse routing-shaped and config-shaped FABulous FASM features."""
    document = parse_fabulous_fasm(
        """
        # routing for net '$PACKER_VCC'
        X0Y5.VCC0.B_T
        X1Y5.A.INIT1[15:0] = 'b0101000110100000
        X2Y5.WW4BEG12.WW4END8 { module = "top" } # annotation/comment
        """
    )

    features = document.query()

    assert len(features) == 3
    assert features[0].raw == "X0Y5.VCC0.B_T"
    assert features[0].feature_type is FabulousFasmFeatureType.ROUTING
    assert features[0].coordinate == (0, 5)
    assert features[0].source == "VCC0"
    assert features[0].destination == "B_T"
    assert features[1].feature_type is FabulousFasmFeatureType.CONFIG
    assert features[1].parts == ("X1Y5", "A", "INIT1")
    assert features[1].address == "[15:0]"
    assert features[1].value == "'b0101000110100000"
    assert features[2].raw == "X2Y5.WW4BEG12.WW4END8"


def test_query_returns_feature_lists_from_predicates() -> None:
    """Filter parsed FASM features with one generic query method."""
    document = parse_fabulous_fasm(
        """
        X0Y5.VCC0.B_T
        X1Y5.A.INIT1[15:0] = 'b0101000110100000
        """
    )

    config_features = document.query(
        lambda feature: feature.feature_type is FabulousFasmFeatureType.CONFIG
    )
    tile_features = document.query(lambda feature: feature.tile_x == 0)

    assert isinstance(config_features, list)
    assert [feature.raw for feature in config_features] == [
        "X1Y5.A.INIT1[15:0] = 'b0101000110100000"
    ]
    assert [feature.raw for feature in tile_features] == ["X0Y5.VCC0.B_T"]


def test_parse_fabulous_fasm_annotates_features_from_graph() -> None:
    """Resolve routing and config features with graph metadata."""
    pip = _pip(
        owner=(0, 5),
        source=(0, 5, "VCC0"),
        destination=(0, 5, "B_T"),
        name="VCC0.B_T",
        kind=RoutingPipKind.INTERNAL_MATRIX,
        tile_type="W_IO",
    )
    document = parse_fabulous_fasm(
        """
        X0Y5.VCC0.B_T
        X1Y5.A.INIT1[15:0] = 'b0101000110100000
        """,
        graph=_FakeGraph(
            tile_types={(0, 5): "W_IO", (1, 5): "LUT5F"},
            pips=[pip],
        ),
    )

    routing, config = document.query()

    assert routing.resolved
    assert routing.feature_type is FabulousFasmFeatureType.ROUTING
    assert routing.tile_type == "W_IO"
    assert routing.pip_kind is RoutingPipKind.INTERNAL_MATRIX
    assert routing.pip == pip
    assert config.resolved
    assert config.feature_type is FabulousFasmFeatureType.CONFIG
    assert config.tile_type == "LUT5F"
    assert config.pip is None


def test_parse_fabulous_fasm_stops_after_requested_pips_are_indexed() -> None:
    """Avoid consuming unrelated graph PIPs after all FASM PIPs are found."""
    requested = _pip(
        owner=(0, 5),
        source=(0, 5, "VCC0"),
        destination=(0, 5, "B_T"),
        name="VCC0.B_T",
        kind=RoutingPipKind.INTERNAL_MATRIX,
        tile_type="W_IO",
    )
    unrelated = _pip(
        owner=(1, 5),
        source=(1, 5, "E1END0"),
        destination=(1, 5, "LA_I0"),
        name="E1END0.LA_I0",
        kind=RoutingPipKind.INTERNAL_MATRIX,
        tile_type="LUT5F",
    )
    graph = _FakeGraph(
        tile_types={(0, 5): "W_IO"},
        pips=[requested, unrelated],
    )

    document = parse_fabulous_fasm("X0Y5.VCC0.B_T", graph=graph)

    assert document.query()[0].pip == requested
    assert graph.iterated_pips == 1


def test_routing_matrix_features_for_tile_type_filters_instances() -> None:
    """Return internal matrix features for every instance of one tile type."""
    matrix_a = _pip(
        owner=(1, 5),
        source=(1, 5, "E1END0"),
        destination=(1, 5, "LA_I0"),
        name="E1END0.LA_I0",
        kind=RoutingPipKind.INTERNAL_MATRIX,
        tile_type="LUT5F",
    )
    matrix_b = _pip(
        owner=(2, 5),
        source=(2, 5, "E1END0"),
        destination=(2, 5, "LA_I0"),
        name="E1END0.LA_I0",
        kind=RoutingPipKind.INTERNAL_MATRIX,
        tile_type="LUT5F",
    )
    matrix_c = _pip(
        owner=(2, 5),
        source=(2, 5, "E2END0"),
        destination=(2, 5, "LA_I1"),
        name="E2END0.LA_I1",
        kind=RoutingPipKind.INTERNAL_MATRIX,
        tile_type="LUT5F",
    )
    external = _pip(
        owner=(2, 5),
        source=(2, 5, "WW4BEG12"),
        destination=(1, 5, "WW4END8"),
        name="WW4BEG12.WW4END8",
        kind=RoutingPipKind.EXTERNAL_WIRE,
        tile_type="LUT5F",
    )
    document = parse_fabulous_fasm(
        """
        X1Y5.E1END0.LA_I0
        X2Y5.E1END0.LA_I0
        X2Y5.E2END0.LA_I1
        X2Y5.WW4BEG12.WW4END8
        """,
        graph=_FakeGraph(
            tile_types={(1, 5): "LUT5F", (2, 5): "LUT5F"},
            pips=[matrix_a, matrix_b, matrix_c, external],
        ),
    )

    all_matrix = document.routing_matrix_features_for_tile_type("LUT5F")
    filtered_matrix = document.routing_matrix_features_for_tile_type(
        "LUT5F",
        where=lambda feature: feature.tile_x == 2,
    )
    unique_matrix = document.routing_matrix_features_for_tile_type(
        "LUT5F",
        filter_unique_pips=True,
    )
    unique_filtered_matrix = document.routing_matrix_features_for_tile_type(
        "LUT5F",
        where=lambda feature: feature.tile_x == 2,
        filter_unique_pips=True,
    )
    used_matrix = document.used_switch_matrix_for_tile_type("LUT5F")
    used_matrix_with_override = document.used_switch_matrix_for_tile_type(
        "LUT5F",
        active_pip_value=1,
    )
    used_filtered_matrix = document.used_switch_matrix_for_tile_type(
        "LUT5F",
        where=lambda feature: feature.tile_x == 2,
    )

    assert [feature.pip for feature in all_matrix] == [matrix_a, matrix_b, matrix_c]
    assert [feature.pip for feature in filtered_matrix] == [matrix_b, matrix_c]
    assert [feature.pip for feature in unique_matrix] == [matrix_a, matrix_c]
    assert [feature.pip for feature in unique_filtered_matrix] == [matrix_b, matrix_c]
    assert used_matrix.tile_type == "LUT5F"
    assert used_matrix.rows == ["E1END0", "E2END0"]
    assert used_matrix.columns == ["LA_I0", "LA_I1"]
    assert used_matrix.matrix == [[8.0, 0.0], [0.0, 8.0]]
    assert used_matrix_with_override.matrix == [[1.0, 0.0], [0.0, 1.0]]
    assert used_filtered_matrix.matrix == [[8.0, 0.0], [0.0, 8.0]]

    with pytest.raises(ValueError, match="active_pip_value"):
        document.used_switch_matrix_for_tile_type("LUT5F", active_pip_value=0)


def test_parse_fabulous_fasm_uses_owner_tile_for_external_pip_annotation() -> None:
    """Resolve external PIPs by owner tile and PIP name."""
    pip = _pip(
        owner=(2, 5),
        source=(2, 5, "WW4BEG12"),
        destination=(1, 5, "WW4END8"),
        name="WW4BEG12.WW4END8",
        kind=RoutingPipKind.EXTERNAL_WIRE,
        tile_type="LUT5F",
    )
    document = parse_fabulous_fasm(
        "X2Y5.WW4BEG12.WW4END8",
        graph=_FakeGraph(tile_types={(2, 5): "LUT5F"}, pips=[pip]),
    )

    feature = document.query()[0]

    assert feature.resolved
    assert feature.feature_type is FabulousFasmFeatureType.ROUTING
    assert feature.pip_kind is RoutingPipKind.EXTERNAL_WIRE
    assert feature.pip == pip


def test_routing_external_features_for_tile_type_filters_instances() -> None:
    """Return external features and PIPs for every instance of one tile type."""
    external_a = _pip(
        owner=(1, 5),
        source=(1, 5, "WW4BEG12"),
        destination=(0, 5, "WW4END8"),
        name="WW4BEG12.WW4END8",
        kind=RoutingPipKind.EXTERNAL_WIRE,
        tile_type="LUT5F",
    )
    external_b = _pip(
        owner=(2, 5),
        source=(2, 5, "WW4BEG12"),
        destination=(1, 5, "WW4END8"),
        name="WW4BEG12.WW4END8",
        kind=RoutingPipKind.EXTERNAL_WIRE,
        tile_type="LUT5F",
    )
    external_c = _pip(
        owner=(2, 5),
        source=(2, 5, "EE2BEG0"),
        destination=(3, 5, "EE2END0"),
        name="EE2BEG0.EE2END0",
        kind=RoutingPipKind.EXTERNAL_WIRE,
        tile_type="LUT5F",
    )
    unused_duplicate_a = _pip(
        owner=(1, 5),
        source=(1, 5, "SS1BEG0"),
        destination=(0, 5, "SS1END0"),
        name="SS1BEG0.SS1END0",
        kind=RoutingPipKind.EXTERNAL_WIRE,
        tile_type="LUT5F",
    )
    unused_duplicate_b = _pip(
        owner=(2, 5),
        source=(2, 5, "SS1BEG0"),
        destination=(1, 5, "SS1END0"),
        name="SS1BEG0.SS1END0",
        kind=RoutingPipKind.EXTERNAL_WIRE,
        tile_type="LUT5F",
    )
    unused_unique = _pip(
        owner=(2, 5),
        source=(2, 5, "NN2BEG0"),
        destination=(3, 5, "NN2END0"),
        name="NN2BEG0.NN2END0",
        kind=RoutingPipKind.EXTERNAL_WIRE,
        tile_type="LUT5F",
    )
    matrix = _pip(
        owner=(2, 5),
        source=(2, 5, "E1END0"),
        destination=(2, 5, "LA_I0"),
        name="E1END0.LA_I0",
        kind=RoutingPipKind.INTERNAL_MATRIX,
        tile_type="LUT5F",
    )
    graph = _FakeGraph(
        tile_types={(1, 5): "LUT5F", (2, 5): "LUT5F"},
        pips=[
            external_a,
            external_b,
            external_c,
            matrix,
            unused_duplicate_a,
            unused_duplicate_b,
            unused_unique,
        ],
    )
    document = parse_fabulous_fasm(
        """
        X1Y5.WW4BEG12.WW4END8
        X2Y5.WW4BEG12.WW4END8
        X2Y5.EE2BEG0.EE2END0
        X2Y5.E1END0.LA_I0
        """,
        graph=graph,
    )

    all_external = document.routing_external_features_for_tile_type("LUT5F")
    filtered_external = document.routing_external_features_for_tile_type(
        "LUT5F",
        where=lambda feature: feature.tile_x == 2,
    )
    unique_external = document.routing_external_features_for_tile_type(
        "LUT5F",
        filter_unique_pips=True,
    )
    used_external = document.used_external_pips_for_tile_type("LUT5F")
    used_filtered_external = document.used_external_pips_for_tile_type(
        "LUT5F",
        where=lambda feature: feature.tile_x == 2,
    )
    unused_external = document.unused_external_pips_for_tile_type(graph, "LUT5F")
    unused_external_instances = document.unused_external_pips_for_tile_type(
        graph,
        "LUT5F",
        filter_unique_pips=False,
    )

    assert [feature.pip for feature in all_external] == [
        external_a,
        external_b,
        external_c,
    ]
    assert [feature.pip for feature in filtered_external] == [
        external_b,
        external_c,
    ]
    assert [feature.pip for feature in unique_external] == [external_a, external_c]
    assert used_external == [external_a, external_c]
    assert used_filtered_external == [external_b, external_c]
    assert unused_external == [unused_duplicate_a, unused_unique]
    assert unused_external_instances == [
        unused_duplicate_a,
        unused_duplicate_b,
        unused_unique,
    ]


def test_parse_fabulous_fasm_raises_when_graph_cannot_resolve_tile() -> None:
    """Reject graph annotation when a feature coordinate has no placed tile."""
    with pytest.raises(FabulousFasmResolveError, match="unplaced tile X9Y9"):
        parse_fabulous_fasm("X9Y9.VCC0.B_T", graph=_FakeGraph())


@dataclass
class _FakeGraph:
    """Small graph test double for FASM annotation."""

    tile_types: dict[tuple[int, int], str] | None = None
    pips: list[RoutingPip] | None = None
    iterated_pips: int = 0

    def iter_active_pips(
        self,
        where: Callable[[RoutingPip], bool] | None = None,
    ) -> Iterator[RoutingPip]:
        """Yield fake active PIPs."""
        for pip in self.pips or []:
            self.iterated_pips += 1
            if where is None or where(pip):
                yield pip

    def tile_type_at(self, x: int, y: int) -> str | None:
        """Return a fake tile type."""
        return (self.tile_types or {}).get((x, y))


def _pip(
    *,
    owner: tuple[int, int],
    source: tuple[int, int, str],
    destination: tuple[int, int, str],
    name: str,
    kind: RoutingPipKind,
    tile_type: str,
) -> RoutingPip:
    """Create a concrete routing PIP for parser tests."""
    return RoutingPip(
        pip_id=None,
        kind=kind,
        source=RoutingEndpoint(source[0], source[1], source[2]),
        destination=RoutingEndpoint(destination[0], destination[1], destination[2]),
        delay=8.0,
        name=name,
        owner_tile=owner,
        tile_type=tile_type,
        resource_key=RoutingResourceKey(
            tile_type=tile_type,
            kind=kind,
            source_name=source[2],
            destination_name=destination[2],
        ),
    )
