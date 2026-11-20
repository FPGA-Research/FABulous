"""Tests for the `BelPort` views of a `Bel`."""

from pathlib import Path

import pytest

from fabulous.fabric_definition.bel import Bel
from fabulous.fabric_definition.define import IO
from tests.conftest import make_pad_bel


def make_bel(
    internal: list[tuple[str, IO]],
    *,
    external: list[tuple[str, IO]] | None = None,
    prefix: str = "LA_",
    user_clk: bool = False,
) -> Bel:
    """Build a LUT-style BEL with the given ports.

    Parameters
    ----------
    internal : list[tuple[str, IO]]
        Internal ports as `(prefixed name, direction)`.
    external : list[tuple[str, IO]] | None
        External ports as `(prefixed name, direction)`. Defaults to none.
    prefix : str
        BEL prefix.
    user_clk : bool
        Whether the BEL has a `UserCLK` port.

    Returns
    -------
    Bel
        The BEL.
    """
    return Bel(
        src=Path("LUT4c_frame_config_dffesr.v"),
        prefix=prefix,
        module_name="LUT4c_frame_config_dffesr",
        internal=internal,
        external=external or [],
        configPort=[],
        sharedPort=[("UserCLK", IO.INPUT)] if user_clk else [],
        configBit=0,
        belMap={},
        userCLK=user_clk,
        ports_vectors={},
        carry={},
        localShared={},
    )


@pytest.mark.parametrize("prefix", ["", "LA_"])
def test_bel_ports_follow_the_parsed_ports(prefix: str) -> None:
    bel = make_bel(
        [
            (f"{prefix}I0", IO.INPUT),
            (f"{prefix}O", IO.OUTPUT),
            (f"{prefix}I1", IO.INPUT),
        ],
        external=[(f"{prefix}PAD_I", IO.INPUT), (f"{prefix}PAD_O", IO.OUTPUT)],
        prefix=prefix,
    )

    assert [p.name for p in bel.input_ports] == [f"{prefix}I0", f"{prefix}I1"]
    assert [p.name for p in bel.output_ports] == [f"{prefix}O"]
    assert [p.name for p in bel.external_input_ports] == [f"{prefix}PAD_I"]
    assert [p.name for p in bel.external_output_ports] == [f"{prefix}PAD_O"]
    internal_ports = bel.input_ports + bel.output_ports
    external_ports = bel.external_input_ports + bel.external_output_ports
    assert {p.prefix for p in internal_ports + external_ports} == {prefix}
    assert {p.width for p in internal_ports + external_ports} == {1}
    assert not any(p.external for p in internal_ports)
    assert all(p.external for p in external_ports)
    assert all(p.is_input for p in bel.input_ports + bel.external_input_ports)
    assert all(p.is_output for p in bel.output_ports + bel.external_output_ports)


@pytest.mark.parametrize("user_clk", [True, False])
def test_user_clk_port(user_clk: bool) -> None:
    bel = make_bel([("LA_I0", IO.INPUT)], user_clk=user_clk)

    if user_clk:
        assert bel.user_clk_port is not None
        assert bel.user_clk_port.name == "UserCLK"
        assert bel.user_clk_port.is_clock
    else:
        assert bel.user_clk_port is None


@pytest.mark.parametrize(
    ("internal", "external"),
    [
        pytest.param([("I0", IO.INPUT)], [], id="internal"),
        pytest.param([], [("PAD", IO.INPUT)], id="external"),
    ],
)
def test_port_without_the_bel_prefix_is_rejected(
    internal: list[tuple[str, IO]], external: list[tuple[str, IO]]
) -> None:
    with pytest.raises(ValueError, match="does not start with prefix LA_"):
        make_bel(internal, external=external)


def test_identically_built_bels_are_equal() -> None:
    internal = [("LA_I0", IO.INPUT), ("LA_O", IO.OUTPUT)]

    assert make_bel(internal) == make_bel(internal)


@pytest.mark.parametrize(
    ("keep_vector_ports", "input_pins", "output_pins"),
    [
        pytest.param(False, ["D0", "D1", "EN"], ["Q0", "Q1"], id="split"),
        pytest.param(True, ["D[0]", "D[1]", "EN"], ["Q[0]", "Q[1]"], id="vector"),
    ],
)
def test_bel_port_pin_names_follow_keep_vector_ports(
    keep_vector_ports: bool, input_pins: list[str], output_pins: list[str]
) -> None:
    """A bit of a kept vector port is the pin `D[0]` on the wire `LA_D0`.

    A scalar port is the same pin either way, and the wire names never change.
    """
    bel = Bel(
        src=Path("my_bel.v"),
        prefix="LA_",
        module_name="my_bel",
        internal=[
            ("LA_D0", IO.INPUT),
            ("LA_D1", IO.INPUT),
            ("LA_EN", IO.INPUT),
            ("LA_Q0", IO.OUTPUT),
            ("LA_Q1", IO.OUTPUT),
        ],
        external=[],
        configPort=[],
        sharedPort=[],
        configBit=0,
        belMap={},
        userCLK=False,
        ports_vectors={
            "internal": {
                "D": (IO.INPUT, 2),
                "EN": (IO.INPUT, 1),
                "Q": (IO.OUTPUT, 2),
            },
            "external": {},
            "config": {},
            "shared": {},
        },
        carry={},
        localShared={},
        keep_vector_ports=keep_vector_ports,
    )

    assert [p.pin_name for p in bel.input_ports] == input_pins
    assert [p.pin_name for p in bel.output_ports] == output_pins
    assert [p.name for p in bel.input_ports] == ["LA_D0", "LA_D1", "LA_EN"]
    assert [p.name for p in bel.output_ports] == ["LA_Q0", "LA_Q1"]


@pytest.mark.parametrize(
    ("keep_vector_ports", "inputs", "outputs"),
    [
        pytest.param(
            False,
            [("A_DI0", 1), ("A_DI1", 1), ("A_DI2", 1), ("A_DI3", 1), ("A_EN", 1)],
            [("A_DO0", 1), ("A_DO1", 1), ("A_DO2", 1), ("A_DO3", 1)],
            id="split",
        ),
        pytest.param(
            True, [("A_DI", 4), ("A_EN", 1)], [("A_DO", 4)], id="vector_ports"
        ),
    ],
)
def test_external_vector_ports_follow_keep_vector_ports(
    keep_vector_ports: bool,
    inputs: list[tuple[str, int]],
    outputs: list[tuple[str, int]],
) -> None:
    """An external vector port is one wide port only when the BEL opts in."""
    bel = make_pad_bel(keep_vector_ports)

    assert [(p.name, p.width) for p in bel.external_input_ports] == inputs
    assert [(p.name, p.width) for p in bel.external_output_ports] == outputs
    external_ports = bel.external_input_ports + bel.external_output_ports
    assert all(p.external and p.prefix == "A_" for p in external_ports)
