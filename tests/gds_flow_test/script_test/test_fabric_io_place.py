"""Integration tests for fabric_io_place - calls the actual io_place function.

This test file calls the actual io_place() function from fabric_io_place.py
by mocking only the external dependencies (odb, OdbReader) at the module level.

This tests the real production code, not a reimplementation.
"""

import contextlib
from types import SimpleNamespace

import pytest
from conftest import (
    MockBlockIoPlace,
    MockBTermIoPlace,
    MockDie,
    MockITerm,
    MockLayer,
    MockMaster,
    MockMTerm,
    MockNetIoPlace,
    MockReaderIoPlace,
    MockRect,
    MockTechIoPlace,
    PinPlacementRecorder,
)


@pytest.fixture
def _io_place_setup(
    mock_odb_io_place: SimpleNamespace, monkeypatch: pytest.MonkeyPatch
) -> None:  # noqa: ANN001, ANN202
    """Setup io_place with mocked OdbReader and odb module."""

    from fabulous.backend.gds.script import fabric_io_place

    # Patch odb module using monkeypatch
    monkeypatch.setattr(fabric_io_place, "odb", mock_odb_io_place)


def _call_io_place(
    reader: MockReaderIoPlace,
    monkeypatch: pytest.MonkeyPatch,
    **kwargs: object,
) -> None:
    """Call the actual io_place function with mocked dependencies."""
    from librelane.scripts.odbpy.reader import OdbReader

    from fabulous.backend.gds.script import fabric_io_place

    # Mock OdbReader to return our mock reader
    def mock_odbreader_init(self: object, *_args: object, **_: object) -> None:
        for attr in dir(reader):
            if not attr.startswith("_"):
                with contextlib.suppress(AttributeError):
                    setattr(self, attr, getattr(reader, attr))

    monkeypatch.setattr(OdbReader, "__init__", mock_odbreader_init)
    io_place_func = fabric_io_place.io_place

    # Get the actual function from Click command
    actual_func = (
        io_place_func.callback if hasattr(io_place_func, "callback") else io_place_func
    )

    # Call with parameters
    actual_func(
        input_db="dummy.odb",
        input_lefs=[],
        config_path=None,
        reader=reader,
        ver_layer=str(kwargs.get("ver_layer", "V")),
        hor_layer=str(kwargs.get("hor_layer", "H")),
        ver_width_mult=float(kwargs.get("ver_width_mult", 2.0)),  # type: ignore
        hor_width_mult=float(kwargs.get("hor_width_mult", 2.0)),  # type: ignore
        hor_length=kwargs.get("hor_length"),
        ver_length=kwargs.get("ver_length"),
        hor_extension=float(kwargs.get("hor_extension", 0.0)),  # type: ignore
        ver_extension=float(kwargs.get("ver_extension", 0.0)),  # type: ignore
        verbose=bool(kwargs.get("verbose", False)),
    )


@pytest.mark.usefixtures("_io_place_setup")
def test_io_place_north_side_placement(
    pin_placement_recorder: PinPlacementRecorder,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Test pin placement on NORTH side - validates coordinates and layer selection."""
    h_layer = MockLayer(width=50, area=10000, name="H")
    v_layer = MockLayer(width=50, area=10000, name="V")
    tech = MockTechIoPlace(h_layer, v_layer)
    die = MockDie(0, 0, 1000, 1000)

    master = MockMaster(100, 100)
    mterm_bbox = MockRect(25, 100, 50, 0)
    iterm_bbox = MockRect(400, 400, 100, 100)
    mterm = MockMTerm(mterm_bbox, master)
    iterm = MockITerm(iterm_bbox, mterm)
    net = MockNetIoPlace("north_pin", [iterm])
    bterm = MockBTermIoPlace("north_pin", net)

    block = MockBlockIoPlace(die, [bterm])
    reader = MockReaderIoPlace(100.0, tech, block)

    _call_io_place(
        reader,
        monkeypatch,
        ver_layer="V",
        hor_layer="H",
        ver_width_mult=2.0,
        hor_width_mult=2.0,
        hor_length=None,
        ver_length=None,
        hor_extension=0.0,
        ver_extension=0.0,
        verbose=False,
    )

    assert len(pin_placement_recorder.placements) == 1
    name, layer, x1, y1, x2, y2 = pin_placement_recorder.placements[0]

    # Verify pin name and layer selection
    assert name == "north_pin"
    assert layer == "V", "NORTH side should use vertical layer"

    # Verify Y coordinates - pin should extend to die boundary
    assert y2 == 1000, f"Pin should extend to die yMax (1000), got {y2}"

    # Verify X coordinates - pin should be centered on iterm
    # iterm_bbox is at (400, 400) with width 100, so center is at 450
    # Pin width = layer_width (50) * width_mult (2.0) = 100
    # So pin should span from center - width/2 to center + width/2
    assert x1 == 400, f"Pin x1 should be 400 (iterm x), got {x1}"

    # Verify pin width is correct (using width multiplier)
    expected_width = v_layer.getWidth() * 2.0  # width_mult = 2.0
    actual_width = x2 - x1
    assert actual_width == expected_width, (
        f"Pin width should be {expected_width}, got {actual_width}"
    )


@pytest.mark.usefixtures("_io_place_setup")
def test_io_place_all_four_sides(
    pin_placement_recorder: PinPlacementRecorder,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Test that pins can be placed on all four sides with correct coordinates."""
    h_layer = MockLayer(width=50, area=10000, name="H")
    v_layer = MockLayer(width=50, area=10000, name="V")
    tech = MockTechIoPlace(h_layer, v_layer)
    die = MockDie(0, 0, 1000, 1000)

    master = MockMaster(100, 100)

    bterms = []
    for side, bbox in [
        ("north", MockRect(25, 100, 50, 0)),
        ("south", MockRect(25, 0, 50, 0)),
        ("east", MockRect(100, 25, 0, 50)),
        ("west", MockRect(0, 25, 0, 50)),
    ]:
        iterm_bbox = MockRect(400, 400, 100, 100)
        mterm = MockMTerm(bbox, master)
        iterm = MockITerm(iterm_bbox, mterm)
        net = MockNetIoPlace(f"{side}_pin", [iterm])
        bterm = MockBTermIoPlace(f"{side}_pin", net)
        bterms.append(bterm)

    block = MockBlockIoPlace(die, bterms)
    reader = MockReaderIoPlace(100.0, tech, block)

    _call_io_place(
        reader,
        monkeypatch,
        ver_layer="V",
        hor_layer="H",
        ver_width_mult=2.0,
        hor_width_mult=2.0,
        hor_length=None,
        ver_length=None,
        hor_extension=0.0,
        ver_extension=0.0,
        verbose=False,
    )

    assert len(pin_placement_recorder.placements) == 4

    placements_by_name = {
        name: (layer, x1, y1, x2, y2)
        for name, layer, x1, y1, x2, y2 in pin_placement_recorder.placements
    }

    # Verify layer selection based on side
    assert placements_by_name["north_pin"][0] == "V", "North should use vertical layer"
    assert placements_by_name["south_pin"][0] == "V", "South should use vertical layer"
    assert placements_by_name["east_pin"][0] == "H", "East should use horizontal layer"
    assert placements_by_name["west_pin"][0] == "H", "West should use horizontal layer"

    # Verify boundary coordinates for each side
    # North pin should extend to y=1000 (die yMax)
    north_y2 = placements_by_name["north_pin"][4]
    assert north_y2 == 1000, (
        f"North pin should extend to die yMax (1000), got {north_y2}"
    )

    # South pin should extend to y=0 (die yMin)
    south_y1 = placements_by_name["south_pin"][2]
    assert south_y1 == 0, f"South pin should extend to die yMin (0), got {south_y1}"

    # East pin should extend to x=1000 (die xMax)
    east_x2 = placements_by_name["east_pin"][3]
    assert east_x2 == 1000, f"East pin should extend to die xMax (1000), got {east_x2}"

    # West pin should extend to x=0 (die xMin)
    west_x1 = placements_by_name["west_pin"][1]
    assert west_x1 == 0, f"West pin should extend to die xMin (0), got {west_x1}"
