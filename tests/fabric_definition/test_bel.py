"""Tests for the `BelPort` views of a `Bel`."""

from pathlib import Path

import pytest

from fabulous.fabric_definition.bel import Bel
from fabulous.fabric_definition.define import IO


def make_bel(
    internal: list[tuple[str, IO]], *, prefix: str = "LA_", user_clk: bool = False
) -> Bel:
    """Build a LUT-style BEL with the given internal ports.

    Parameters
    ----------
    internal : list[tuple[str, IO]]
        Internal ports as `(prefixed name, direction)`.
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
        external=[],
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
def test_bel_ports_match_the_port_names(prefix: str) -> None:
    bel = make_bel(
        [
            (f"{prefix}I0", IO.INPUT),
            (f"{prefix}I1", IO.INPUT),
            (f"{prefix}O", IO.OUTPUT),
        ],
        prefix=prefix,
    )

    assert [p.name for p in bel.input_ports] == bel.inputs
    assert [p.name for p in bel.output_ports] == bel.outputs
    assert {p.prefix for p in bel.input_ports + bel.output_ports} == {prefix}
    assert all(p.io_direction == IO.INPUT for p in bel.input_ports)
    assert all(p.io_direction == IO.OUTPUT for p in bel.output_ports)
    assert all(p.width == 1 for p in bel.input_ports + bel.output_ports)


@pytest.mark.parametrize("user_clk", [True, False])
def test_user_clk_port(user_clk: bool) -> None:
    bel = make_bel([("LA_I0", IO.INPUT)], user_clk=user_clk)

    if user_clk:
        assert bel.user_clk_port is not None
        assert bel.user_clk_port.name == "UserCLK"
        assert bel.user_clk_port.is_clock
    else:
        assert bel.user_clk_port is None


def test_port_without_the_bel_prefix_is_rejected() -> None:
    with pytest.raises(ValueError, match="does not start with prefix LA_"):
        make_bel([("I0", IO.INPUT)])


def test_ports_do_not_affect_bel_equality() -> None:
    internal = [("LA_I0", IO.INPUT), ("LA_O", IO.OUTPUT)]

    assert make_bel(internal) == make_bel(internal)
