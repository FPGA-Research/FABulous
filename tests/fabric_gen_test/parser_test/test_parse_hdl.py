"""Tests for the BEL module attributes read by `parseBelFile`."""

from pathlib import Path

import pytest
from pytest_mock import MockerFixture

from fabulous.custom_exception import InvalidBelDefinition
from fabulous.fabric_definition.bel import Bel
from fabulous.fabric_definition.define import BelRole
from fabulous.fabric_definition.yosys_obj import YosysModule
from fabulous.fabric_generator.parser.parse_hdl import parseBelFile


def parse_with_attributes(
    mocker: MockerFixture,
    attributes: dict[str, str | int],
    *,
    config_bits: int = 0,
    name: str = "pass_bel",
) -> Bel:
    """Parse a BEL whose Yosys module has the module `attributes`.

    The module has one input `I`, one output `O` and `config_bits` config bits,
    so no HDL tool runs.

    Parameters
    ----------
    mocker : MockerFixture
        Patches the Yosys front end.
    attributes : dict[str, str | int]
        The module attributes.
    config_bits : int
        Width of the `ConfigBits` port; no port when 0.
    name : str
        The BEL type name, the stem of its file.

    Returns
    -------
    Bel
        The parsed BEL.
    """
    ports = {
        "I": {"direction": "input", "bits": [2]},
        "O": {"direction": "output", "bits": [3]},
    }
    netnames = {
        "I": {"hide_name": 0, "bits": [2], "attributes": {}},
        "O": {"hide_name": 0, "bits": [3], "attributes": {}},
    }
    if config_bits:
        bits = list(range(4, 4 + config_bits))
        ports["ConfigBits"] = {"direction": "input", "bits": bits}
        netnames["ConfigBits"] = {"hide_name": 0, "bits": bits, "attributes": {}}
    module = YosysModule(
        attributes={"top": 1, **attributes},
        parameter_default_values={},
        ports=ports,
        cells={},
        memories={},
        netnames=netnames,
    )
    yosys_json = mocker.Mock(modules={name: module})
    yosys_json.getTopModule.return_value = (name, module)
    mocker.patch(
        "fabulous.fabric_generator.parser.parse_hdl.YosysJson",
        return_value=yosys_json,
    )
    return parseBelFile(Path(f"{name}.v"), "A_")


@pytest.mark.parametrize(
    ("attributes", "role", "is_fabric_pin"),
    [
        ({"FABulous": 1, "ROLE": "LOGIC_CELL"}, BelRole.LOGIC_CELL, False),
        ({"FABulous": 1, "ROLE": "FABRIC_INPUT"}, BelRole.FABRIC_INPUT, True),
        ({"FABulous": 1, "ROLE": "FABRIC_INOUT"}, BelRole.FABRIC_INOUT, True),
        ({"FABulous": 1, "ROLE": "OTHER"}, BelRole.OTHER, False),
        # GHDL lowercases the attribute names of some VHDL BELs.
        ({"fabulous": 1, "role": "fabric_output"}, BelRole.FABRIC_OUTPUT, True),
    ],
)
def test_role_comes_from_the_module_attribute(
    mocker: MockerFixture,
    attributes: dict[str, str | int],
    role: BelRole,
    is_fabric_pin: bool,
) -> None:
    """`ROLE` names the BEL's role; the fabric pin roles make it pinnable."""
    bel = parse_with_attributes(mocker, attributes)

    assert bel.role is role
    assert bel.is_fabric_pin is is_fabric_pin


def test_role_is_not_a_belmap_feature(mocker: MockerFixture) -> None:
    """Next to `BelMap`, only the numbered attributes are config features."""
    bel = parse_with_attributes(
        mocker,
        {"FABulous": 1, "BelMap": 1, "ROLE": "FABRIC_INPUT", "I0_reg": 0},
        config_bits=1,
    )

    assert list(bel.belFeatureMap) == ["I0_reg"]
    assert bel.role is BelRole.FABRIC_INPUT


@pytest.mark.parametrize(
    ("name", "role"),
    [
        ("LUT4c_frame_config_dffesr", BelRole.LOGIC_CELL),
        ("InPass4_frame_config_mux", BelRole.FABRIC_INPUT),
        ("OutPass4_frame_config", BelRole.FABRIC_OUTPUT),
        ("IO_1_bidirectional_frame_config_pass", BelRole.FABRIC_INOUT),
        ("MULADD", BelRole.OTHER),
    ],
)
def test_missing_role_is_guessed_from_the_name_with_a_warning(
    mocker: MockerFixture,
    caplog: pytest.LogCaptureFixture,
    name: str,
    role: BelRole,
) -> None:
    """A BEL without `ROLE` keeps the role nextpnr assumed for its name."""
    bel = parse_with_attributes(mocker, {"FABulous": 1}, name=name)

    assert bel.role is role
    assert f"{name}.v has no ROLE attribute" in caplog.text


def test_role_attribute_overrides_the_name(mocker: MockerFixture) -> None:
    """With `ROLE`, the name no longer matters, nor does it pin the BEL."""
    bel = parse_with_attributes(
        mocker, {"FABulous": 1, "ROLE": "OTHER"}, name="InPass4_frame_config"
    )

    assert bel.role is BelRole.OTHER
    assert not bel.is_fabric_pin


@pytest.mark.parametrize("value", ["LUT", 1])
def test_unknown_role_is_rejected(mocker: MockerFixture, value: str | int) -> None:
    """A `ROLE` that names no `BelRole` stops the parse."""
    with pytest.raises(InvalidBelDefinition, match="is not one of"):
        parse_with_attributes(mocker, {"FABulous": 1, "ROLE": value})
