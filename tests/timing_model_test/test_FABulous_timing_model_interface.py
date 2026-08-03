"""Tests for cached BEL timing dispatch through the fabric-level interface."""

import networkx as nx
import pytest
from pytest_mock import MockerFixture

from fabulous.fabric_cad.timing_model.FABulous_timing_model import (
    FABulousTileTimingModel,
)
from fabulous.fabric_cad.timing_model.FABulous_timing_model_interface import (
    FABulousTimingModelInterface,
)
from fabulous.fabric_cad.timing_model.models import (
    BelClockTiming,
    BelClockToOutTiming,
    BelDelayTiming,
    BelSetupHoldTiming,
    BelTiming,
    SDFPathTiming,
    SDFPathType,
    SDFTimingTriplet,
)
from fabulous.fabric_definition.bel import Bel
from fabulous.fabric_definition.define import IO


def _bel(prefix: str = "LA_") -> Bel:
    """Build the stable BEL identity needed by the interface cache.

    Parameters
    ----------
    prefix : str
        Instance prefix distinguishing BELs within one tile macro.

    Returns
    -------
    Bel
        Minimal BEL definition suitable for interface dispatch tests.
    """
    bel = Bel.__new__(Bel)
    bel.name = "LUT4c_frame_config_dffesr"
    bel.module_name = "LUT4c_frame_config_dffesr"
    bel.prefix = prefix
    bel.ports_vectors = {
        "internal": {
            "I": (IO.INPUT, 4),
            "O": (IO.OUTPUT, 1),
            "Ci": (IO.INPUT, 1),
            "Co": (IO.OUTPUT, 1),
        },
        "shared": {"UserCLK": (IO.INPUT, 1)},
    }
    bel.withUserCLK = True
    bel.belFeatureMap = {"INIT": {}, "INIT[1]": {}, "FF": {}, "IOmux": {}}
    bel.carry = {
        "C0": {
            IO.INPUT: f"{prefix}Ci",
            IO.OUTPUT: f"{prefix}Co",
        }
    }
    return bel


def _path_timing(
    path_type: SDFPathType,
    *,
    rise_maximum: float,
    fall_maximum: float,
    setup: float | None = None,
    hold: float | None = None,
) -> SDFPathTiming:
    """Build one path-query result for structural BEL timing tests.

    Parameters
    ----------
    path_type : SDFPathType
        Whether the synthetic path is combinational or sequential.
    rise_maximum : float
        Maximum rising propagation delay.
    fall_maximum : float
        Maximum falling propagation delay.
    setup : float | None
        Optional maximum setup requirement.
    hold : float | None
        Optional maximum hold requirement.

    Returns
    -------
    SDFPathTiming
        Complete synthetic path timing result.
    """
    setup_values: tuple[SDFTimingTriplet, ...] = (
        (SDFTimingTriplet(None, None, setup),) if setup is not None else ()
    )
    hold_values: tuple[SDFTimingTriplet, ...] = (
        (SDFTimingTriplet(None, None, hold),) if hold is not None else ()
    )
    return SDFPathTiming(
        nodes=("source", "sink"),
        components=(),
        path_type=path_type,
        rise=SDFTimingTriplet(None, None, rise_maximum),
        fall=SDFTimingTriplet(None, None, fall_maximum),
        setup=setup_values,
        hold=hold_values,
        register_clock_pin=("clock" if path_type == SDFPathType.SEQUENTIAL else None),
        effective_setup=setup_values,
        effective_hold=hold_values,
        clock_to_output_rise=(
            SDFTimingTriplet(None, None, rise_maximum)
            if path_type == SDFPathType.SEQUENTIAL
            else None
        ),
        clock_to_output_fall=(
            SDFTimingTriplet(None, None, fall_maximum)
            if path_type == SDFPathType.SEQUENTIAL
            else None
        ),
    )


def _timing(delay: float = 3.0) -> BelTiming:
    """Build one immutable combinational timing request.

    Parameters
    ----------
    delay : float
        Placeholder arc delay in nanoseconds.

    Returns
    -------
    BelTiming
        Timing object containing one conditional input-to-output arc.
    """
    return BelTiming(arcs=(BelDelayTiming("I0", "O", delay, condition="FF=0"),))


@pytest.mark.parametrize(
    "method_name", ["bel_timing_structural", "bel_timing_physical"]
)
def test_tile_bel_timing_modes_return_empty_scaffold(
    method_name: str, mocker: MockerFixture
) -> None:
    """Both mode-specific tile methods construct empty BEL timing results."""
    model = FABulousTileTimingModel.__new__(FABulousTileTimingModel)
    model.tile_name = "LUT4AB"
    model.hdlnx_tm_synth = None
    if method_name == "bel_timing_structural":
        model.hdlnx_tm_synth = mocker.Mock()
        model.hdlnx_tm_synth.find_instance_paths_by_regex.return_value = [
            "Inst_LA_LUT4c_frame_config_dffesr"
        ]
        model.hdlnx_tm_synth.resolve_hier_pin.return_value = []

    assert getattr(model, method_name)(_bel()) == BelTiming()

    if method_name == "bel_timing_structural":
        model.hdlnx_tm_synth.find_instance_paths_by_regex.assert_called_once_with(
            r"LA_LUT4c_frame_config_dffesr$"
        )


def test_structural_bel_timing_warns_for_multiple_instance_paths(
    mocker: MockerFixture,
) -> None:
    """Multiple hierarchy matches produce a warning before selecting the first."""
    model = FABulousTileTimingModel.__new__(FABulousTileTimingModel)
    model.tile_name = "LUT4AB"
    model.hdlnx_tm_synth = mocker.Mock()
    model.hdlnx_tm_synth.find_instance_paths_by_regex.return_value = [
        "Tile_X0Y0_LUT4AB/Inst_LA_LUT4c_frame_config_dffesr",
        "Tile_X1Y0_LUT4AB/Inst_LA_LUT4c_frame_config_dffesr",
    ]
    model.hdlnx_tm_synth.resolve_hier_pin.return_value = []
    warning = mocker.patch(
        "fabulous.fabric_cad.timing_model.FABulous_timing_model.logger.warning"
    )

    assert model.bel_timing_structural(_bel()) == BelTiming()
    warning.assert_called_once()


def test_structural_bel_timing_maps_nextpnr_pins_to_verilog_pins(
    mocker: MockerFixture,
) -> None:
    """Vectorized nextpnr pins map back to indexed Verilog module pins."""
    model = FABulousTileTimingModel.__new__(FABulousTileTimingModel)
    model.tile_name = "LUT4AB"
    model.hdlnx_tm_synth = mocker.Mock()
    model.hdlnx_tm_synth.find_instance_paths_by_regex.return_value = [
        "Inst_LA_LUT4c_frame_config_dffesr"
    ]
    model.hdlnx_tm_synth.resolve_hier_pin.side_effect = lambda pin: [f"{pin}/std_cell"]
    model.hdlnx_tm_synth.query_timing_paths.side_effect = nx.NetworkXNoPath

    assert model.bel_timing_structural(_bel()) == BelTiming()

    resolved_module_pins: list[str] = [
        call.args[0] for call in model.hdlnx_tm_synth.resolve_hier_pin.call_args_list
    ]
    assert resolved_module_pins == [
        "Inst_LA_LUT4c_frame_config_dffesr/I[0]",
        "Inst_LA_LUT4c_frame_config_dffesr/I[1]",
        "Inst_LA_LUT4c_frame_config_dffesr/I[2]",
        "Inst_LA_LUT4c_frame_config_dffesr/I[3]",
        "Inst_LA_LUT4c_frame_config_dffesr/Ci",
        "Inst_LA_LUT4c_frame_config_dffesr/O",
        "Inst_LA_LUT4c_frame_config_dffesr/Co",
        "Inst_LA_LUT4c_frame_config_dffesr/UserCLK",
        "Inst_LA_LUT4c_frame_config_dffesr/ConfigBits[0]",
        "Inst_LA_LUT4c_frame_config_dffesr/ConfigBits[1]",
        "Inst_LA_LUT4c_frame_config_dffesr/ConfigBits[2]",
        "Inst_LA_LUT4c_frame_config_dffesr/ConfigBits[3]",
    ]


@pytest.mark.parametrize(
    ("bel_name", "expected_clock_to_output_port"),
    [
        pytest.param("LUT4c_frame_config_dffesr", "Q", id="fabulous-lc"),
        pytest.param("CUSTOM", "O", id="custom-bel"),
    ],
)
def test_structural_bel_timing_evaluates_every_input_output_pair(
    mocker: MockerFixture,
    bel_name: str,
    expected_clock_to_output_port: str,
) -> None:
    """Translate the first combinational and sequential paths into BEL arcs.

    Parameters
    ----------
    mocker : MockerFixture
        Pytest fixture used to construct the synthetic timing model and capture logs.
    bel_name : str
        BEL name used to select the nextpnr clock-to-output port.
    expected_clock_to_output_port : str
        Expected real or pseudo clock-to-output port.
    """
    model = FABulousTileTimingModel.__new__(FABulousTileTimingModel)
    model.tile_name = "LUT4AB"
    model.hdlnx_tm_synth = mocker.Mock()
    bel = _bel()
    bel.name = bel_name
    bel.module_name = bel_name
    bel_instance_path: str = f"Inst_LA_{bel_name}"
    model.hdlnx_tm_synth.find_instance_paths_by_regex.return_value = [bel_instance_path]
    resolved_pins: dict[str, list[str]] = {
        f"{bel_instance_path}/I[0]": ["input_a", "input_b"],
        f"{bel_instance_path}/O": ["output_a", "output_b"],
        f"{bel_instance_path}/Co": ["carry_output"],
        f"{bel_instance_path}/UserCLK": ["clock"],
    }
    model.hdlnx_tm_synth.resolve_hier_pin.side_effect = lambda pin: resolved_pins.get(
        pin, []
    )
    first_combinational = _path_timing(
        SDFPathType.COMBINATIONAL,
        rise_maximum=0.2,
        fall_maximum=0.3,
    )
    ignored_combinational = _path_timing(
        SDFPathType.COMBINATIONAL,
        rise_maximum=8.0,
        fall_maximum=9.0,
    )
    first_sequential = _path_timing(
        SDFPathType.SEQUENTIAL,
        rise_maximum=0.6,
        fall_maximum=0.7,
        setup=2.5,
        hold=0.1,
    )
    ignored_sequential = _path_timing(
        SDFPathType.SEQUENTIAL,
        rise_maximum=6.0,
        fall_maximum=7.0,
        setup=5.0,
        hold=1.0,
    )
    carry_path = _path_timing(
        SDFPathType.COMBINATIONAL,
        rise_maximum=0.35,
        fall_maximum=0.4,
    )

    def query_timing_paths(
        source: str,
        sink: str,
        *,
        clock_pin: str | None = None,
    ) -> list[SDFPathTiming]:
        """Return controlled path alternatives for one resolved leaf-pin pair.

        Parameters
        ----------
        source : str
            Resolved source leaf pin.
        sink : str
            Resolved sink leaf pin.
        clock_pin : str | None
            Optional resolved clock pin used for effective sequential timing.

        Returns
        -------
        list[SDFPathTiming]
            Ordered path-query results for the requested pair.

        Raises
        ------
        nx.NetworkXNoPath
            If the test pair has no timing path.
        """
        assert clock_pin in (None, "clock")
        if (source, sink) == ("input_a", "output_a"):
            return [
                first_combinational,
                ignored_combinational,
                first_sequential,
                ignored_sequential,
            ]
        if (source, sink) == ("input_a", "carry_output"):
            return [carry_path]
        raise nx.NetworkXNoPath

    model.hdlnx_tm_synth.query_timing_paths.side_effect = query_timing_paths
    info = mocker.patch(
        "fabulous.fabric_cad.timing_model.FABulous_timing_model.logger.info"
    )

    assert model.bel_timing_structural(bel) == BelTiming(
        arcs=(
            BelClockTiming(clock="CLK", condition="FF=1"),
            BelDelayTiming(source="I0", sink="O", delay=0.3, condition="FF=0"),
            BelDelayTiming(
                source="I0",
                sink="Co",
                delay=0.4,
                condition="FF=0",
            ),
            BelSetupHoldTiming(
                port="I0",
                clock="CLK",
                setup=2.5,
                hold=0.1,
                condition="FF=1",
            ),
            BelClockToOutTiming(
                port=expected_clock_to_output_port,
                clock="CLK",
                delay=0.7,
                condition="FF=1",
            ),
        )
    )
    info.assert_any_call(
        f"Timing extraction for tile: LUT4AB, BEL: LA_{bel_name} "
        f"(10 input/output pairs)"
    )
    info.assert_any_call(
        f"BEL timing | progress=1/10 | type={bel_name} | "
        "input=I0 | output=O | combinational=0.3 ns | "
        "clock-to-output=0.7 ns | setup=2.5 ns | hold=0.1 ns"
    )
    info.assert_any_call(
        f"Completed timing extraction for tile: LUT4AB, BEL: LA_{bel_name} "
        f"(5 timing arcs)"
    )
    model.hdlnx_tm_synth.single_delay.assert_not_called()


def test_structural_bel_timing_treats_custom_carry_ports_as_regular_ports(
    mocker: MockerFixture,
) -> None:
    """Treat annotated custom carry ports as ordinary timing endpoints.

    Parameters
    ----------
    mocker : MockerFixture
        Pytest fixture used to construct the synthetic timing model.
    """
    model = FABulousTileTimingModel.__new__(FABulousTileTimingModel)
    model.tile_name = "CUSTOM"
    model.hdlnx_tm_synth = mocker.Mock()
    model.hdlnx_tm_synth.find_instance_paths_by_regex.return_value = ["Inst_X_CUSTOM"]
    resolved_pins: dict[str, list[str]] = {
        "Inst_X_CUSTOM/CIN": ["carry_input"],
        "Inst_X_CUSTOM/COUT": ["carry_output"],
    }
    model.hdlnx_tm_synth.resolve_hier_pin.side_effect = lambda pin: resolved_pins.get(
        pin, []
    )
    model.hdlnx_tm_synth.query_timing_paths.return_value = [
        _path_timing(
            SDFPathType.COMBINATIONAL,
            rise_maximum=0.4,
            fall_maximum=0.5,
        )
    ]
    bel = _bel("X_")
    bel.name = "CUSTOM"
    bel.module_name = "CUSTOM"
    bel.ports_vectors = {
        "internal": {
            "CIN": (IO.INPUT, 1),
            "COUT": (IO.OUTPUT, 1),
        }
    }
    bel.belFeatureMap = {}
    bel.carry = {
        "C0": {
            IO.INPUT: "X_CIN",
            IO.OUTPUT: "X_COUT",
        },
        "duplicate": {
            IO.INPUT: "X_CIN",
            IO.OUTPUT: "X_COUT",
        },
    }

    assert model.bel_timing_structural(bel) == BelTiming(
        arcs=(
            BelDelayTiming(
                source="CIN",
                sink="COUT",
                delay=0.5,
            ),
        )
    )


def test_interface_bel_timing_caches_by_tile_and_bel_identity(
    mocker: MockerFixture,
) -> None:
    """Repeated requests reuse one tile-model BEL timing result."""
    tile_model = mocker.Mock()
    characterized = _timing(1.25)
    tile_model.bel_timing.return_value = characterized
    interface = FABulousTimingModelInterface.__new__(FABulousTimingModelInterface)
    interface.timing_models = {"LUT4AB": tile_model}
    interface.bel_timing_cache = {}
    bel = _bel()

    first = interface.bel_timing("LUT4AB", bel)
    second = interface.bel_timing("LUT4AB", bel)

    assert first is characterized
    assert second is characterized
    tile_model.bel_timing.assert_called_once_with(bel)


def test_interface_bel_timing_keeps_multiple_bel_prefixes_separate(
    mocker: MockerFixture,
) -> None:
    """Two instances of one BEL module do not collide in the cache."""
    tile_model = mocker.Mock()
    tile_model.bel_timing.return_value = BelTiming()
    interface = FABulousTimingModelInterface.__new__(FABulousTimingModelInterface)
    interface.timing_models = {"LUT4AB": tile_model}
    interface.bel_timing_cache = {}
    interface.bel_timing("LUT4AB", _bel("LA_"))
    interface.bel_timing("LUT4AB", _bel("LB_"))

    assert tile_model.bel_timing.call_count == 2


def test_interface_bel_timing_rejects_unknown_tile() -> None:
    """BEL timing requests require a timing model for the named tile type."""
    interface = FABulousTimingModelInterface.__new__(FABulousTimingModelInterface)
    interface.timing_models = {}
    interface.bel_timing_cache = {}

    with pytest.raises(ValueError, match="UNKNOWN"):
        interface.bel_timing("UNKNOWN", _bel())
