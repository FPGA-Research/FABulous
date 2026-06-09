from pathlib import Path

import pytest

import fabulous.routing_model.tile_timing_model as tm_mod
from fabulous.fabric_definition.cell_spec import CellSpec, StdCellLibrary
from fabulous.fabric_definition.yosys_obj import InstanceRef, YosysCellDetails
from fabulous.routing_model.graph_algorithms import DelayType
from fabulous.routing_model.tile_timing_model import (
    FABulousTileTimingModel,
    InternalPipCacheEntry,
    TimingModelMode,
)


class FakeModule:
    """Minimal stand-in for a YosysModule with a controllable pin->net map.

    The refactored generator reads instance nets via ``InstanceRef.pin_nets()``
    (which delegates to ``module.pin_nets(inst_name)``) and groups switch-matrix
    nets via ``netlist.modules[name].pin_nets(inst)``; this fake supplies both
    without needing a full bit-level Yosys netlist.
    """

    def __init__(
        self, cells: dict[str, object], pin_nets_map: dict[str, dict[str, str]]
    ) -> None:
        self.cells = cells
        self._pin_nets_map = pin_nets_map

    def pin_nets(self, inst_name: str) -> dict[str, list[str]]:
        # The real YosysModule.pin_nets returns one net name per bit; these
        # fakes describe scalar pins, so wrap each net in a one-element list.
        return {pin: [net] for pin, net in self._pin_nets_map[inst_name].items()}


def make_instance_ref(
    path: str,
    pin_nets: dict[str, str] | None = None,
    module_name: str = "tile_switch_matrix",
) -> InstanceRef:
    """Build an InstanceRef whose `pin_nets()` returns the given pin->net map.

    The instance's cell connections (and therefore
    ``switch_matrix_instance.cell.connections.keys()``) follow the pin names in
    `pin_nets`.
    """
    pin_nets = pin_nets or {}
    inst_name = path.rsplit("/", 1)[-1]
    cell = YosysCellDetails(
        hide_name=0,
        type="MUX",
        parameters={},
        attributes={},
        connections={pin: [] for pin in pin_nets},
    )
    module = FakeModule(cells={inst_name: cell}, pin_nets_map={inst_name: pin_nets})
    return InstanceRef(
        path=path,
        module=module,
        module_name=module_name,
        inst_name=inst_name,
        cell=cell,
    )


class DummyTile:
    def __init__(self, name: object) -> None:
        self.name = name


class DummySuperTile:
    def __init__(self, name: object, tiles: list[DummyTile]) -> None:
        self.name = name
        self.tiles = tiles


class DummyFabric:
    def __init__(self, super_tiles: list[DummySuperTile] | None = None) -> None:
        self._super_tiles = super_tiles or []

    def get_super_tile_containing(self, tile_name: str) -> DummySuperTile | None:
        for super_tile in self._super_tiles:
            if any(tile.name == tile_name for tile in super_tile.tiles):
                return super_tile
        return None


class DummyNetlistTM:
    def __init__(self) -> None:
        self.output_ports = set()
        self.input_ports = set()
        # The generator calls the module-level graph helpers as
        # ``single_delay(model.timing_graph, ...)`` /
        # ``earliest_common_nodes(model.graph, ...)`` and reaches netlist queries
        # via ``model.netlist.<query>``. Pointing graph/timing_graph/netlist all
        # at the mock itself lets the ``_delegate_graph_helpers`` fixture forward
        # each helper, and lets the navigation stubs below double as the netlist.
        self.graph = self
        self.timing_graph = self
        self.netlist = self
        self.delay_type_str = DelayType.MAX_ALL
        # Netlist module table backing the inlined switch-matrix net grouping;
        # tests populate it for the extract path.
        self.modules: dict[str, FakeModule] = {}

    # Netlist (YosysJson) query surface used by the generator. ``modules`` (set in
    # __init__) backs the inlined switch-matrix net grouping; walk_instances backs
    # the inlined swm-mux search. Tests override these as needed.
    def find_instances_by_regex(
        self, _regex: object, filter_regex: object = None
    ) -> list[object]:
        _ = filter_regex
        return []

    def find_verilog_modules_regex(self, _regex: object) -> list[object]:
        return []

    def walk_instances(self, _module_name: object = None) -> list[object]:
        return []

    def net_to_pin_paths_for_instance_resolved(
        self, _inst: object
    ) -> dict[object, object]:
        return {}

    def single_delay(self, _src: object, _dst: object) -> float:
        return 0.0

    def nearest_ports_from_instance_pin_nets(
        self, _inst_path: object, reverse: bool = False, num_ports: int = 1
    ) -> tuple[dict[str, list[str]], list[str]]:
        _ = (reverse, num_ports)
        return {}, []

    def earliest_common_nodes(
        self,
        sources: object,
        mode: str = "max",
        sentinel: object = None,
        prefer_sentinel_for_single_source: bool = False,
        follow_steps_to_sentinel: int = 0,
    ) -> tuple[list[str], int, dict[str, object]]:
        _ = (
            sources,
            mode,
            sentinel,
            prefer_sentinel_for_single_source,
            follow_steps_to_sentinel,
        )
        return ["X"], 1, {}

    def follow_first_fanout_from_pins(
        self, hier_pin_path: object, num_follow: int = 1
    ) -> str:
        _ = num_follow
        assert hier_pin_path == "X"
        return "X"

    def path_to_nearest_target_sentinel(
        self, _src: object, _targets: object
    ) -> tuple[list[str], object | None]:
        return [], None


@pytest.fixture(autouse=True)
def _delegate_graph_helpers(monkeypatch: pytest.MonkeyPatch) -> None:
    """Route the generator's module-level graph helpers to the mock model methods.

    The generator no longer calls these as methods on the timing model; it calls
    the free functions from `graph_algorithms` (imported into the generator
    module) passing ``model.graph`` / ``model.timing_graph``. The mocks set those
    attributes to themselves, so each helper just forwards to the matching method,
    keeping the per-test stubs and their argument assertions intact.
    """
    monkeypatch.setattr(
        tm_mod,
        "single_delay",
        lambda timing_graph, src, dst, _delay_type=None: timing_graph.single_delay(
            src, dst
        ),
    )
    monkeypatch.setattr(
        tm_mod,
        "earliest_common_nodes",
        lambda graph, **kwargs: graph.earliest_common_nodes(**kwargs),
    )
    monkeypatch.setattr(
        tm_mod,
        "follow_first_fanout_from_pins",
        lambda graph, **kwargs: graph.follow_first_fanout_from_pins(**kwargs),
    )
    monkeypatch.setattr(
        tm_mod,
        "path_to_nearest_target_sentinel",
        lambda graph, src, targets: graph.path_to_nearest_target_sentinel(src, targets),
    )


@pytest.fixture
def bare_model(tmp_path: Path) -> FABulousTileTimingModel:
    m = FABulousTileTimingModel.__new__(FABulousTileTimingModel)
    m.fabric = DummyFabric([])
    m.tile_name = "TILE_A"
    m.unique_tile_name = "TILE_A"
    m.is_in_which_super_tile = None
    m.verilog_files = None
    m.mode = TimingModelMode.STRUCTURAL
    m.consider_wire_delay = False
    m.delay_type = DelayType.MAX_ALL
    m.delay_scaling_factor = 1.0
    m.project_dir = tmp_path
    m.library = StdCellLibrary(
        liberty_files=[tmp_path / "x.lib"],
        cells={"buffer": [CellSpec(cell="buf", input_ports=["A"], output_ports=["X"])]},
    )
    m.netlist_tm_synth = DummyNetlistTM()
    m.netlist_tm_phys = DummyNetlistTM()
    m.switch_matrix_instance = make_instance_ref("tile_inst_switch_matrix")
    m.switch_matrix_module_name = "tile_switch_matrix"
    m.internal_pips_grouped_by_inst = {}
    m.internal_pips = []
    m.internal_pip_cache = {}
    return m


def test_init_sets_attributes_and_calls_helpers(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    called = {"init_tm": 0, "extract": 0}

    def fake_init_tm(self: FABulousTileTimingModel) -> None:
        called["init_tm"] += 1
        self.netlist_tm_synth = "SYNTH"
        self.netlist_tm_phys = "PHYS"

    def fake_extract(self: FABulousTileTimingModel) -> None:
        called["extract"] += 1
        self.switch_matrix_instance = make_instance_ref("swm_inst")
        self.switch_matrix_module_name = "swm_mod"
        self.internal_pips_grouped_by_inst = {"u0": ["A", "B"]}
        self.internal_pips = ["A", "B"]

    monkeypatch.setattr(
        FABulousTileTimingModel, "_initialize_timing_models", fake_init_tm
    )
    monkeypatch.setattr(
        FABulousTileTimingModel, "_extract_switch_matrix_info", fake_extract
    )

    fabric = DummyFabric([])

    obj = FABulousTileTimingModel(
        fabric,
        verilog_files=[tmp_path / "a.v"],
        tile_name="TILE_A",
        mode=TimingModelMode.STRUCTURAL,
        consider_wire_delay=False,
        delay_type=DelayType.MAX_ALL,
        delay_scaling_factor=1.0,
        library=StdCellLibrary(),
    )

    assert obj.fabric is fabric
    assert obj.tile_name == "TILE_A"
    assert obj.unique_tile_name == "TILE_A"
    assert obj.is_in_which_super_tile is None
    assert obj.verilog_files == [tmp_path / "a.v"]
    assert obj.mode == TimingModelMode.STRUCTURAL
    assert obj.consider_wire_delay is False
    assert obj.delay_type == DelayType.MAX_ALL
    assert obj.delay_scaling_factor == 1.0
    assert obj.netlist_tm_synth == "SYNTH"
    assert obj.netlist_tm_phys == "PHYS"
    assert obj.switch_matrix_instance.path == "swm_inst"
    assert obj.switch_matrix_module_name == "swm_mod"
    assert obj.internal_pips == ["A", "B"]
    assert obj.internal_pip_cache == {}
    assert called == {"init_tm": 1, "extract": 1}


def test_init_inside_supertile_resolves_unique_name(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        FABulousTileTimingModel,
        "_initialize_timing_models",
        lambda _self: None,
    )
    monkeypatch.setattr(
        FABulousTileTimingModel,
        "_extract_switch_matrix_info",
        lambda _self: None,
    )

    st = DummySuperTile("SUPER_X", [DummyTile("TILE_A"), DummyTile("TILE_B")])
    fabric = DummyFabric([st])

    obj = FABulousTileTimingModel(
        fabric,
        verilog_files=[],
        tile_name="TILE_A",
        mode=TimingModelMode.STRUCTURAL,
        consider_wire_delay=False,
        delay_type=DelayType.MAX_ALL,
        delay_scaling_factor=1.0,
        library=StdCellLibrary(),
    )

    assert obj.unique_tile_name == "SUPER_X"
    assert obj.is_in_which_super_tile == "SUPER_X"


def _patch_init_helpers(
    bare_model: FABulousTileTimingModel,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    created: list[dict[str, object]],
) -> None:
    """Patch NetlistTimingModel so init records its constructions.

    `created` collects the keyword arguments of each NetlistTimingModel construction
    (synthesis-level first, physical-level second). The model's Verilog sources are
    supplied directly on ``bare_model`` to mirror the constructor-injected list.
    """

    class FakeNetlistTimingModel:
        def __init__(self, **kwargs: object) -> None:
            created.append(kwargs)

    bare_model.verilog_files = [tmp_path / "rtl.v"]
    monkeypatch.setattr(tm_mod, "NetlistTimingModel", FakeNetlistTimingModel)


def _physical_netlist(tmp_path: Path, tile: str) -> Path:
    return tmp_path / "Tile" / tile / "macro" / "final_views" / "nl" / f"{tile}.nl.v"


def _physical_spef(tmp_path: Path, tile: str) -> Path:
    return (
        tmp_path
        / "Tile"
        / tile
        / "macro"
        / "final_views"
        / "spef"
        / "nom"
        / f"{tile}.nom.spef"
    )


def test_initialize_timing_models_structural_builds_synth_only(
    tmp_path: Path,
    bare_model: FABulousTileTimingModel,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    created: list[dict[str, object]] = []
    _patch_init_helpers(bare_model, monkeypatch, tmp_path, created)

    bare_model.mode = TimingModelMode.STRUCTURAL
    bare_model.delay_type = DelayType.MAX_ALL

    bare_model._initialize_timing_models()  # noqa: SLF001

    assert len(created) == 1
    synth = created[0]
    assert synth["verilog_files"] == [tmp_path / "rtl.v"]
    assert synth["top_name"] == "TILE_A"
    assert synth["library"] is bare_model.library
    assert synth["is_gate_level"] is False
    assert synth["spef_files"] is None
    assert synth["delay_type_str"] == DelayType.MAX_ALL


def test_initialize_timing_models_physical_without_wire_delay(
    tmp_path: Path,
    bare_model: FABulousTileTimingModel,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    created: list[dict[str, object]] = []
    _patch_init_helpers(bare_model, monkeypatch, tmp_path, created)

    bare_model.unique_tile_name = "TILE_A"
    bare_model.mode = TimingModelMode.PHYSICAL
    bare_model.consider_wire_delay = False

    bare_model._initialize_timing_models()  # noqa: SLF001

    assert len(created) == 2
    phys = created[1]
    assert phys["is_gate_level"] is True
    assert phys["verilog_files"] == _physical_netlist(tmp_path, "TILE_A")
    assert phys["spef_files"] is None


def test_initialize_timing_models_physical_with_wire_delay(
    tmp_path: Path,
    bare_model: FABulousTileTimingModel,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    created: list[dict[str, object]] = []
    _patch_init_helpers(bare_model, monkeypatch, tmp_path, created)

    bare_model.unique_tile_name = "TILE_A"
    bare_model.mode = TimingModelMode.PHYSICAL
    bare_model.consider_wire_delay = True

    bare_model._initialize_timing_models()  # noqa: SLF001

    assert len(created) == 2
    assert created[1]["spef_files"] == _physical_spef(tmp_path, "TILE_A")


def test_extract_switch_matrix_info_regular_success(
    bare_model: FABulousTileTimingModel,
) -> None:
    synth = DummyNetlistTM()
    swm_inst = make_instance_ref(
        "tile_inst_switch_matrix", pin_nets={"A": "a", "B": "b", "Y": "y"}
    )
    synth.find_instances_by_regex = lambda _regex: [swm_inst]
    synth.find_verilog_modules_regex = lambda _regex: ["tile_switch_matrix"]
    synth.modules = {
        "tile_switch_matrix": FakeModule(
            cells={"mux0": None},
            pin_nets_map={"mux0": {"i0": "A", "i1": "B", "o": "Y"}},
        )
    }

    bare_model.netlist_tm_synth = synth
    bare_model.is_in_which_super_tile = None

    bare_model._extract_switch_matrix_info()  # noqa: SLF001

    assert bare_model.switch_matrix_instance.path == "tile_inst_switch_matrix"
    assert bare_model.switch_matrix_module_name == "tile_switch_matrix"
    assert bare_model.internal_pips_grouped_by_inst == {"mux0": ["A", "B", "Y"]}
    assert bare_model.internal_pips == ["A", "B", "Y"]


def test_extract_switch_matrix_info_none_found_returns_without_loading(
    bare_model: FABulousTileTimingModel,
) -> None:
    synth = DummyNetlistTM()
    synth.find_instances_by_regex = lambda _regex: []
    synth.find_verilog_modules_regex = lambda _regex: []

    bare_model.netlist_tm_synth = synth
    bare_model.switch_matrix_instance = None
    bare_model.switch_matrix_module_name = None
    bare_model.internal_pips_grouped_by_inst = None
    bare_model.internal_pips = None

    bare_model._extract_switch_matrix_info()  # noqa: SLF001

    assert bare_model.switch_matrix_instance == []
    assert bare_model.switch_matrix_module_name == []
    assert bare_model.internal_pips_grouped_by_inst is None
    assert bare_model.internal_pips is None


def test_extract_switch_matrix_info_regular_multiple_raises(
    bare_model: FABulousTileTimingModel,
) -> None:
    synth = DummyNetlistTM()
    synth.find_instances_by_regex = lambda _regex: [
        make_instance_ref("a"),
        make_instance_ref("b"),
    ]
    synth.find_verilog_modules_regex = lambda _regex: ["m1", "m2"]
    bare_model.netlist_tm_synth = synth
    bare_model.is_in_which_super_tile = None

    with pytest.raises(
        ValueError,
        match="Multiple switch matrix instances or modules found for a non-SuperTile",
    ):
        bare_model._extract_switch_matrix_info()  # noqa: SLF001


def test_extract_switch_matrix_info_supertile_success(
    bare_model: FABulousTileTimingModel,
) -> None:
    synth = DummyNetlistTM()
    synth.find_instances_by_regex = lambda _regex: [
        make_instance_ref("OTHER_switch_matrix"),
        make_instance_ref(
            "TILE_A_switch_matrix", pin_nets={"I0": "i0", "I1": "i1", "O": "o"}
        ),
    ]
    synth.find_verilog_modules_regex = lambda _regex: [
        "OTHER_switch_matrix_mod",
        "TILE_A_switch_matrix_mod",
    ]
    synth.modules = {
        "TILE_A_switch_matrix_mod": FakeModule(
            cells={"mux0": None},
            pin_nets_map={"mux0": {"a": "I0", "b": "I1", "c": "O"}},
        )
    }

    bare_model.netlist_tm_synth = synth
    bare_model.tile_name = "TILE_A"
    bare_model.unique_tile_name = "SUPER_X"
    bare_model.is_in_which_super_tile = "SUPER_X"

    bare_model._extract_switch_matrix_info()  # noqa: SLF001

    assert bare_model.switch_matrix_instance.path == "TILE_A_switch_matrix"
    assert bare_model.switch_matrix_module_name == "TILE_A_switch_matrix_mod"
    assert bare_model.internal_pips == ["I0", "I1", "O"]


def test_extract_switch_matrix_info_supertile_none_raises(
    bare_model: FABulousTileTimingModel,
) -> None:
    synth = DummyNetlistTM()
    synth.find_instances_by_regex = lambda _regex: [
        make_instance_ref("OTHER_switch_matrix")
    ]
    synth.find_verilog_modules_regex = lambda _regex: ["OTHER_switch_matrix_mod"]

    bare_model.netlist_tm_synth = synth
    bare_model.tile_name = "TILE_A"
    bare_model.unique_tile_name = "SUPER_X"
    bare_model.is_in_which_super_tile = "SUPER_X"

    with pytest.raises(
        ValueError,
        match="No switch matrix instance or module found for SuperTile SUPER_X",
    ):
        bare_model._extract_switch_matrix_info()  # noqa: SLF001


def test_extract_switch_matrix_info_supertile_multiple_raises(
    bare_model: FABulousTileTimingModel,
) -> None:
    synth = DummyNetlistTM()
    synth.find_instances_by_regex = lambda _regex: [
        make_instance_ref("TILE_A_swm0"),
        make_instance_ref("TILE_A_swm1"),
    ]
    synth.find_verilog_modules_regex = lambda _regex: ["TILE_A_mod0", "TILE_A_mod1"]

    bare_model.netlist_tm_synth = synth
    bare_model.tile_name = "TILE_A"
    bare_model.unique_tile_name = "SUPER_X"
    bare_model.is_in_which_super_tile = "SUPER_X"

    with pytest.raises(
        ValueError,
        match=(
            "Multiple switch matrix instances or modules found Tile TILE_A "
            "in SuperTile SUPER_X"
        ),
    ):
        bare_model._extract_switch_matrix_info()  # noqa: SLF001


def test_is_tile_internal_pip_true_and_false(
    bare_model: FABulousTileTimingModel,
) -> None:
    bare_model.internal_pips_grouped_by_inst = {
        "mux0": ["A", "B", "Y"],
        "mux1": ["C", "D", "Z"],
    }

    assert bare_model.is_tile_internal_pip("A", "Y") is True
    assert bare_model.is_tile_internal_pip("A", "Z") is False


def test_is_tile_internal_pip_false_when_mapping_none(
    bare_model: FABulousTileTimingModel,
) -> None:
    bare_model.internal_pips_grouped_by_inst = None
    assert bare_model.is_tile_internal_pip("A", "Y") is False


def test_is_tile_internal_pip_false_when_same_src_and_dst(
    bare_model: FABulousTileTimingModel,
) -> None:
    bare_model.internal_pips_grouped_by_inst = {"mux0": ["A", "Y"]}
    assert bare_model.is_tile_internal_pip("A", "A") is False


def test_internal_pip_delay_structural_no_mux_raises_value_error(
    bare_model: FABulousTileTimingModel,
) -> None:
    synth = DummyNetlistTM()
    synth.walk_instances = lambda _module_name=None: []  # no mux carries both nets

    bare_model.netlist_tm_synth = synth

    with pytest.raises(ValueError, match="No switch matrix mux instance found"):
        bare_model.internal_pip_delay_structural("A", "Y")


def test_internal_pip_delay_structural_success_and_caches(
    bare_model: FABulousTileTimingModel,
) -> None:
    class Synth(DummyNetlistTM):
        def __init__(self) -> None:
            super().__init__()
            self.walk_calls = 0
            self.resolve_calls = 0

        def walk_instances(self, _module_name: object = None) -> list[InstanceRef]:
            self.walk_calls += 1
            # Both muxes carry pip nets A and Y inside the switch-matrix instance.
            return [
                make_instance_ref(
                    "tile_inst_switch_matrix/mux0", pin_nets={"A": "A", "Y": "Y"}
                ),
                make_instance_ref(
                    "tile_inst_switch_matrix/mux1", pin_nets={"A": "A", "Y": "Y"}
                ),
            ]

        def net_to_pin_paths_for_instance_resolved(
            self, _inst: object
        ) -> dict[str, list[str]]:
            self.resolve_calls += 1
            return {
                "A": ["mux0/A0", "mux0/A1"],
                "Y": ["mux0/Y0", "mux0/Y1"],
            }

        def single_delay(self, _src: object, _dst: object) -> float:
            return 0.123

    synth = Synth()
    bare_model.netlist_tm_synth = synth
    bare_model.internal_pip_cache = {}

    delay = bare_model.internal_pip_delay_structural("A", "Y")

    assert delay == 0.123
    assert synth.walk_calls == 1
    assert synth.resolve_calls == 1
    assert "Y" in bare_model.internal_pip_cache
    cache_entry = bare_model.internal_pip_cache["Y"]
    assert isinstance(cache_entry, InternalPipCacheEntry)
    assert [m.path for m in cache_entry.swm_mux_for_pips] == [
        "tile_inst_switch_matrix/mux0",
        "tile_inst_switch_matrix/mux1",
    ]
    assert cache_entry.swm_mux_resolved == {
        "A": ["mux0/A0", "mux0/A1"],
        "Y": ["mux0/Y0", "mux0/Y1"],
    }


def test_internal_pip_delay_structural_cache_hit_reuses_cached_values(
    bare_model: FABulousTileTimingModel,
) -> None:
    class Synth(DummyNetlistTM):
        def __init__(self) -> None:
            super().__init__()
            self.walk_calls = 0
            self.resolve_calls = 0

        def walk_instances(self, _module_name: object = None) -> list[InstanceRef]:
            self.walk_calls += 1
            return [make_instance_ref("should_not_be_used")]

        def net_to_pin_paths_for_instance_resolved(
            self, _inst: object
        ) -> dict[str, list[str]]:
            self.resolve_calls += 1
            return {"bad": ["bad"]}

        def single_delay(self, _src: object, _dst: object) -> float:
            return 1.5

    synth = Synth()
    bare_model.netlist_tm_synth = synth
    bare_model.internal_pip_cache = {
        "Y": InternalPipCacheEntry(
            swm_mux_for_pips=[make_instance_ref("cached_mux")],
            swm_nearest_ports_in=None,
            swm_nearest_ports_out=None,
            swm_output_pin=None,
            swm_mux_resolved={
                "A": ["CACHED_A"],
                "Y": ["CACHED_Y"],
            },
        )
    }

    delay = bare_model.internal_pip_delay_structural("A", "Y")

    assert delay == 1.5
    assert synth.walk_calls == 0
    assert synth.resolve_calls == 0


def test_internal_pip_delay_physical_cache_miss_multiple_ports(
    bare_model: FABulousTileTimingModel,
) -> None:
    class Synth(DummyNetlistTM):
        def __init__(self) -> None:
            super().__init__()
            self.walk_calls = 0
            self.nearest_calls = 0

        def walk_instances(self, _module_name: object = None) -> list[InstanceRef]:
            self.walk_calls += 1
            return [
                make_instance_ref(
                    "tile_inst_switch_matrix/mux0", pin_nets={"A": "A", "Y": "Y"}
                ),
                make_instance_ref(
                    "tile_inst_switch_matrix/mux1", pin_nets={"A": "A", "Y": "Y"}
                ),
            ]

        def nearest_ports_from_instance_pin_nets(
            self,
            _inst_path: object,
            reverse: bool = False,
            num_ports: int = 1,
        ) -> tuple[dict[str, list[str]], list[str]]:
            _ = num_ports
            self.nearest_calls += 1
            if reverse:
                return (
                    {"A": ["IN_A"], "Y": ["IN_Y"]},
                    ["IN_A", "IN_Y"],
                )
            return (
                {"Y": ["OUT_REF"]},
                ["OUT_REF"],
            )

    class Phys(DummyNetlistTM):
        def __init__(self) -> None:
            super().__init__()
            self.earliest_calls = 0

        def earliest_common_nodes(
            self,
            sources: object,
            mode: str = "max",
            sentinel: object = None,
            prefer_sentinel_for_single_source: bool = False,
            follow_steps_to_sentinel: int = 0,
        ) -> tuple[list[str], int, dict[str, object]]:
            self.earliest_calls += 1
            assert sources == ["IN_A", "IN_Y"]
            assert mode == "max"
            assert sentinel is None
            assert prefer_sentinel_for_single_source is True
            assert follow_steps_to_sentinel == 3
            return ["OUT2", "OUT1"], 3, {"dummy": 1}

        def single_delay(self, _src: object, _dst: object) -> float:
            return 0.456

    synth = Synth()
    phys = Phys()

    bare_model.netlist_tm_synth = synth
    bare_model.netlist_tm_phys = phys
    bare_model.internal_pip_cache = {}

    delay = bare_model.internal_pip_delay_physical("A", "Y")

    assert delay == 0.456
    assert synth.walk_calls == 1
    assert synth.nearest_calls == 1
    assert phys.earliest_calls == 1
    assert "Y" in bare_model.internal_pip_cache
    cache_entry = bare_model.internal_pip_cache["Y"]
    assert isinstance(cache_entry, InternalPipCacheEntry)
    assert [m.path for m in cache_entry.swm_mux_for_pips] == [
        "tile_inst_switch_matrix/mux0",
        "tile_inst_switch_matrix/mux1",
    ]
    assert cache_entry.swm_nearest_ports_in == (
        {"A": ["IN_A"], "Y": ["IN_Y"]},
        ["IN_A", "IN_Y"],
    )
    assert cache_entry.swm_nearest_ports_out is None
    assert cache_entry.swm_output_pin == ["OUT2", "OUT1"]
    assert cache_entry.swm_mux_resolved is None


def test_internal_pip_delay_physical_cache_miss_single_input_uses_output_reference_and_caches(  # noqa: E501
    bare_model: FABulousTileTimingModel,
) -> None:
    class Synth(DummyNetlistTM):
        def __init__(self) -> None:
            super().__init__()
            self.nearest_calls = 0

        def walk_instances(self, _module_name: object = None) -> list[InstanceRef]:
            return [
                make_instance_ref(
                    "tile_inst_switch_matrix/mux0", pin_nets={"A": "A", "Y": "Y"}
                )
            ]

        def nearest_ports_from_instance_pin_nets(
            self,
            _inst_path: object,
            reverse: bool = False,
            num_ports: int = 1,
        ) -> tuple[dict[str, list[str]], list[str]]:
            _ = num_ports
            self.nearest_calls += 1
            if reverse:
                return (
                    {"A": ["IN_A"], "Y": ["IN_Y"]},
                    ["IN_A"],
                )
            return (
                {"Y": ["OUT_REF"]},
                ["OUT_REF"],
            )

    class Phys(DummyNetlistTM):
        def earliest_common_nodes(
            self,
            sources: object,
            mode: str = "max",
            sentinel: object = None,
            prefer_sentinel_for_single_source: bool = False,
            follow_steps_to_sentinel: int = 0,
        ) -> tuple[list[str], int, dict[str, object]]:
            _ = mode
            assert sources == ["IN_A"]
            assert sentinel == "OUT_REF"
            assert prefer_sentinel_for_single_source is True
            assert follow_steps_to_sentinel == 3
            return ["PHYS_OUT"], 1, {}

        def single_delay(self, _src: object, _dst: object) -> float:
            return 0.789

    synth = Synth()
    phys = Phys()

    bare_model.netlist_tm_synth = synth
    bare_model.netlist_tm_phys = phys
    bare_model.internal_pip_cache = {}

    delay = bare_model.internal_pip_delay_physical("A", "Y")

    assert delay == 0.789
    assert synth.nearest_calls == 2
    cache_entry = bare_model.internal_pip_cache["Y"]
    assert cache_entry.swm_nearest_ports_out == ({"Y": ["OUT_REF"]}, ["OUT_REF"])
    assert cache_entry.swm_output_pin == ["PHYS_OUT"]


def test_internal_pip_delay_physical_cache_hit_reuses_cached_values(
    bare_model: FABulousTileTimingModel,
) -> None:
    class Synth(DummyNetlistTM):
        def __init__(self) -> None:
            super().__init__()
            self.walk_calls = 0
            self.nearest_calls = 0

        def walk_instances(self, _module_name: object = None) -> list[InstanceRef]:
            self.walk_calls += 1
            return [make_instance_ref("should_not_be_used")]

        def nearest_ports_from_instance_pin_nets(
            self,
            _inst_path: object,
            reverse: bool = False,
            num_ports: int = 1,
        ) -> tuple[dict[str, list[str]], list[str]]:
            _ = (reverse, num_ports)
            self.nearest_calls += 1
            return {"bad": ["bad"]}, ["bad"]

    class Phys(DummyNetlistTM):
        def __init__(self) -> None:
            super().__init__()
            self.earliest_calls = 0

        def earliest_common_nodes(
            self,
            sources: object,
            mode: str = "max",
            sentinel: object = None,
            prefer_sentinel_for_single_source: bool = False,
            follow_steps_to_sentinel: int = 0,
        ) -> tuple[list[str], int, dict[str, object]]:
            _ = (
                sources,
                mode,
                sentinel,
                prefer_sentinel_for_single_source,
                follow_steps_to_sentinel,
            )
            self.earliest_calls += 1
            return ["should_not_be_used"], 0, {}

        def single_delay(self, _src: object, _dst: object) -> float:
            return 1.234

    synth = Synth()
    phys = Phys()

    bare_model.netlist_tm_synth = synth
    bare_model.netlist_tm_phys = phys
    bare_model.internal_pip_cache = {
        "Y": InternalPipCacheEntry(
            swm_mux_for_pips=[make_instance_ref("cached_mux")],
            swm_nearest_ports_in=(
                {"A": ["CACHED_IN"], "Y": ["CACHED_DST"]},
                ["CACHED_IN", "CACHED_DST"],
            ),
            swm_nearest_ports_out=None,
            swm_output_pin=["CACHED_PHYS_OUT"],
            swm_mux_resolved=None,
        )
    }

    delay = bare_model.internal_pip_delay_physical("A", "Y")

    assert delay == 1.234
    assert synth.walk_calls == 0
    assert synth.nearest_calls == 0
    assert phys.earliest_calls == 0


def test_external_pip_delay_structural_output_port_returns_default(
    bare_model: FABulousTileTimingModel,
) -> None:
    synth = DummyNetlistTM()
    synth.output_ports = {"NN2BEG[3]"}
    bare_model.netlist_tm_synth = synth

    assert bare_model.external_pip_delay("NN2BEG3", "X") == 0.001


def test_external_pip_delay_structural_input_port_no_nearest_returns_default_real_input_branch(  # noqa: E501
    bare_model: FABulousTileTimingModel,
) -> None:
    class Synth(DummyNetlistTM):
        def __init__(self) -> None:
            super().__init__()
            self.input_ports = {"NN2BEG[3]"}
            self.output_ports = {"OUT0"}

        def path_to_nearest_target_sentinel(
            self, src: object, targets: object
        ) -> tuple[list[str], object | None]:
            assert src == "NN2BEG[3]"
            assert targets == {"OUT0"}
            return [], None

    bare_model.netlist_tm_synth = Synth()

    assert bare_model.external_pip_delay("NN2BEG3", "X") == 0.001


def test_external_pip_delay_structural_input_port_uses_single_delay(
    bare_model: FABulousTileTimingModel,
) -> None:
    class Synth(DummyNetlistTM):
        def __init__(self) -> None:
            super().__init__()
            self.input_ports = {"NN2BEG[3]"}
            self.output_ports = {"OUT0"}

        def path_to_nearest_target_sentinel(
            self, _src: object, _targets: object
        ) -> tuple[list[str], object | None]:
            return ["NN2BEG[3]", "OUT0"], "OUT0"

        def single_delay(self, _src: object, _dst: object) -> float:
            return 0.222

    bare_model.netlist_tm_synth = Synth()

    assert bare_model.external_pip_delay("NN2BEG3", "X") == 0.222


def test_external_pip_delay_structural_swm_to_swm_without_cache_returns_default(
    bare_model: FABulousTileTimingModel,
) -> None:
    synth = DummyNetlistTM()
    synth.input_ports = {"IN0"}
    synth.output_ports = {"OUT0"}
    bare_model.netlist_tm_synth = synth
    bare_model.internal_pip_cache = {}

    assert bare_model.external_pip_delay("SOME_INTERNAL", "X") == 0.001


def test_external_pip_delay_structural_swm_to_swm_with_cache_uses_follow_and_delay(
    bare_model: FABulousTileTimingModel,
) -> None:
    class Synth(DummyNetlistTM):
        def follow_first_fanout_from_pins(
            self, hier_pin_path: object, num_follow: int = 1
        ) -> str:
            assert hier_pin_path == "SWM_OUT_PIN"
            assert num_follow == 2
            return "NEXT_INPUT_PIN"

        def single_delay(self, src: object, dst: object) -> float:
            assert src == "SWM_OUT_PIN"
            assert dst == "NEXT_INPUT_PIN"
            return 0.444

    bare_model.netlist_tm_synth = Synth()
    bare_model.internal_pip_cache = {
        "PIP_SRC": InternalPipCacheEntry(
            swm_mux_for_pips=["mux0"],
            swm_nearest_ports_in=None,
            swm_nearest_ports_out=None,
            swm_output_pin=None,
            swm_mux_resolved={"PIP_SRC": ["SWM_OUT_PIN"]},
        )
    }

    assert bare_model.external_pip_delay("PIP_SRC", "X") == 0.444


def test_external_pip_delay_structural_swm_to_swm_with_tiny_delay_returns_default(
    bare_model: FABulousTileTimingModel,
) -> None:
    class Synth(DummyNetlistTM):
        def follow_first_fanout_from_pins(
            self, hier_pin_path: object, num_follow: int = 1
        ) -> str:
            assert hier_pin_path == "SWM_OUT_PIN"
            assert num_follow == 2
            return "NEXT_INPUT_PIN"

        def single_delay(self, _src: object, _dst: object) -> float:
            return 0.0

    bare_model.netlist_tm_synth = Synth()
    bare_model.internal_pip_cache = {
        "PIP_SRC": InternalPipCacheEntry(
            swm_mux_for_pips=["mux0"],
            swm_nearest_ports_in=None,
            swm_nearest_ports_out=None,
            swm_output_pin=None,
            swm_mux_resolved={"PIP_SRC": ["SWM_OUT_PIN"]},
        )
    }

    assert bare_model.external_pip_delay("PIP_SRC", "X") == 0.001


def test_external_pip_delay_physical_output_port_returns_default(
    bare_model: FABulousTileTimingModel,
) -> None:
    phys = DummyNetlistTM()
    phys.output_ports = {"NN2BEG[3]"}
    bare_model.netlist_tm_phys = phys

    bare_model.mode = TimingModelMode.PHYSICAL
    assert bare_model.external_pip_delay("NN2BEG3", "X") == 0.001


def test_external_pip_delay_physical_input_port_no_nearest_returns_default_real_input_branch(  # noqa: E501
    bare_model: FABulousTileTimingModel,
) -> None:
    class Phys(DummyNetlistTM):
        def __init__(self) -> None:
            super().__init__()
            self.input_ports = {"NN2BEG[3]"}
            self.output_ports = {"OUT0"}

        def path_to_nearest_target_sentinel(
            self, src: object, targets: object
        ) -> tuple[list[str], object | None]:
            assert src == "NN2BEG[3]"
            assert targets == {"OUT0"}
            return [], None

    bare_model.netlist_tm_phys = Phys()

    bare_model.mode = TimingModelMode.PHYSICAL
    assert bare_model.external_pip_delay("NN2BEG3", "X") == 0.001


def test_external_pip_delay_physical_input_port_uses_single_delay(
    bare_model: FABulousTileTimingModel,
) -> None:
    class Phys(DummyNetlistTM):
        def __init__(self) -> None:
            super().__init__()
            self.input_ports = {"NN2BEG[3]"}
            self.output_ports = {"OUT0"}

        def path_to_nearest_target_sentinel(
            self, _src: object, _targets: object
        ) -> tuple[list[str], object | None]:
            return ["NN2BEG[3]", "OUT0"], "OUT0"

        def single_delay(self, _src: object, _dst: object) -> float:
            return 0.333

    bare_model.netlist_tm_phys = Phys()

    bare_model.mode = TimingModelMode.PHYSICAL
    assert bare_model.external_pip_delay("NN2BEG3", "X") == 0.333


def test_external_pip_delay_physical_swm_to_swm_without_cache_returns_default(
    bare_model: FABulousTileTimingModel,
) -> None:
    phys = DummyNetlistTM()
    phys.input_ports = {"IN0"}
    phys.output_ports = {"OUT0"}
    bare_model.netlist_tm_phys = phys
    bare_model.internal_pip_cache = {}

    bare_model.mode = TimingModelMode.PHYSICAL
    assert bare_model.external_pip_delay("SOME_INTERNAL", "X") == 0.001


def test_external_pip_delay_physical_swm_to_swm_with_cache_uses_follow_and_delay(
    bare_model: FABulousTileTimingModel,
) -> None:
    class Phys(DummyNetlistTM):
        def follow_first_fanout_from_pins(
            self, hier_pin_path: object, num_follow: int = 1
        ) -> str:
            assert hier_pin_path == "PHYS_OUT_PIN"
            assert num_follow == 2
            return "NEXT_PHYS_INPUT"

        def single_delay(self, src: object, dst: object) -> float:
            assert src == "PHYS_OUT_PIN"
            assert dst == "NEXT_PHYS_INPUT"
            return 0.555

    bare_model.netlist_tm_phys = Phys()
    bare_model.internal_pip_cache = {
        "PIP_SRC": InternalPipCacheEntry(
            swm_mux_for_pips=["mux0"],
            swm_nearest_ports_in=None,
            swm_nearest_ports_out=None,
            swm_output_pin=["PHYS_OUT_PIN"],
            swm_mux_resolved=None,
        )
    }

    bare_model.mode = TimingModelMode.PHYSICAL
    assert bare_model.external_pip_delay("PIP_SRC", "X") == 0.555


def test_external_pip_delay_physical_swm_to_swm_with_tiny_delay_returns_default(
    bare_model: FABulousTileTimingModel,
) -> None:
    class Phys(DummyNetlistTM):
        def follow_first_fanout_from_pins(
            self, hier_pin_path: object, num_follow: int = 1
        ) -> str:
            assert hier_pin_path == "PHYS_OUT_PIN"
            assert num_follow == 2
            return "NEXT_PHYS_INPUT"

        def single_delay(self, _src: object, _dst: object) -> float:
            return 0.0

    bare_model.netlist_tm_phys = Phys()
    bare_model.internal_pip_cache = {
        "PIP_SRC": InternalPipCacheEntry(
            swm_mux_for_pips=["mux0"],
            swm_nearest_ports_in=None,
            swm_nearest_ports_out=None,
            swm_output_pin=["PHYS_OUT_PIN"],
            swm_mux_resolved=None,
        )
    }

    bare_model.mode = TimingModelMode.PHYSICAL
    assert bare_model.external_pip_delay("PIP_SRC", "X") == 0.001


def test_internal_pip_delay_dispatch_physical(
    bare_model: FABulousTileTimingModel, monkeypatch: pytest.MonkeyPatch
) -> None:
    bare_model.mode = TimingModelMode.PHYSICAL
    monkeypatch.setattr(bare_model, "internal_pip_delay_physical", lambda _s, _d: 1.23)
    monkeypatch.setattr(
        bare_model, "internal_pip_delay_structural", lambda _s, _d: 9.99
    )

    assert bare_model.internal_pip_delay("A", "Y") == 1.23


def test_internal_pip_delay_dispatch_structural(
    bare_model: FABulousTileTimingModel, monkeypatch: pytest.MonkeyPatch
) -> None:
    bare_model.mode = TimingModelMode.STRUCTURAL
    monkeypatch.setattr(bare_model, "internal_pip_delay_physical", lambda _s, _d: 9.99)
    monkeypatch.setattr(
        bare_model, "internal_pip_delay_structural", lambda _s, _d: 2.34
    )

    assert bare_model.internal_pip_delay("A", "Y") == 2.34


def test_external_pip_delay_selects_model_by_mode(
    bare_model: FABulousTileTimingModel,
) -> None:
    """external_pip_delay reads the phys model in PHYSICAL mode, synth otherwise."""

    class Model(DummyNetlistTM):
        def __init__(self, delay: float) -> None:
            super().__init__()
            self.input_ports = {"NN2BEG[3]"}
            self.output_ports = {"OUT0"}
            self._delay = delay

        def path_to_nearest_target_sentinel(
            self, _src: object, _targets: object
        ) -> tuple[list[str], object | None]:
            return ["NN2BEG[3]", "OUT0"], "OUT0"

        def single_delay(self, _src: object, _dst: object) -> float:
            return self._delay

    bare_model.netlist_tm_synth = Model(0.111)
    bare_model.netlist_tm_phys = Model(0.222)

    bare_model.mode = TimingModelMode.STRUCTURAL
    assert bare_model.external_pip_delay("NN2BEG3", "X") == 0.111

    bare_model.mode = TimingModelMode.PHYSICAL
    assert bare_model.external_pip_delay("NN2BEG3", "X") == 0.222


def test_pip_delay_dispatch_internal_applies_scaling_and_rounding(
    bare_model: FABulousTileTimingModel, monkeypatch: pytest.MonkeyPatch
) -> None:
    bare_model.delay_scaling_factor = 2.5
    monkeypatch.setattr(bare_model, "is_tile_internal_pip", lambda _s, _d: True)
    monkeypatch.setattr(bare_model, "internal_pip_delay", lambda _s, _d: 1.23456)
    monkeypatch.setattr(bare_model, "external_pip_delay", lambda _s, _d: 9.99)

    assert bare_model.pip_delay("A", "Y") == round(1.23456 * 2.5, 3)


def test_pip_delay_dispatch_external_applies_scaling_and_rounding(
    bare_model: FABulousTileTimingModel, monkeypatch: pytest.MonkeyPatch
) -> None:
    bare_model.delay_scaling_factor = 3.0
    monkeypatch.setattr(bare_model, "is_tile_internal_pip", lambda _s, _d: False)
    monkeypatch.setattr(bare_model, "internal_pip_delay", lambda _s, _d: 9.99)
    monkeypatch.setattr(bare_model, "external_pip_delay", lambda _s, _d: 0.33333)

    assert bare_model.pip_delay("A", "Y") == round(0.33333 * 3.0, 3)
