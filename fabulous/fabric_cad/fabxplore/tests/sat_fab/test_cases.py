"""Self-tests and usage examples for sat_fab.

This module contains importable test functions that exercise the main framework features
without adding a command line interface.
"""

from __future__ import annotations

from pathlib import Path
from tempfile import TemporaryDirectory
from typing import TYPE_CHECKING

from fabulous.fabric_cad.fabxplore.modules.sat_fab.cegis import Equiv
from fabulous.fabric_cad.fabxplore.modules.sat_fab.circuit import Circuit
from fabulous.fabric_cad.fabxplore.modules.sat_fab.config import ConfigSpec
from fabulous.fabric_cad.fabxplore.modules.sat_fab.functions import Func

if TYPE_CHECKING:
    from fabulous.fabric_cad.fabxplore.modules.sat_fab.truth import TruthTableSpec


def run_all_tests() -> None:
    """Run all sat_fab self-tests."""
    test_fast_lut_vs_configurable_lut2()
    test_func_truth_table_default_symbolic_config()
    test_truth_block_full_adder()
    test_full_adder_two_manual_lut3()
    test_full_adder_two_lut3_network()
    test_builder_helpers()
    test_configurable_vs_configurable_fixed_left()
    test_fix_pin_and_pinmap()
    test_circuit_local_inputs_do_not_match_by_default()
    test_map_inputs_custom_ports()
    test_route_inputs_lut_with_extra_input()
    test_route_inputs_injective_mapping()
    test_route_outputs_single_target()
    test_route_outputs_multi_target_no_reuse()
    test_route_inputs_and_outputs_together()
    test_route_inputs_lut6_mux4_to_two_lut5_hard_mux()
    test_blif_flut6_implements_mux4_lut6()
    test_blif_flut51p2ps_implements_mux4_lut6()
    test_blif_flut51p2ps_implements_xor6()
    test_blif_flut51p2ps_implements_LUT()
    test_routed_lut_network_mux4()
    test_blif_names_import()
    test_blif_out_of_order_names_import()
    test_blif_out_of_order_subckt_flattening()
    test_blif_prunes_dead_undriven_logic()
    test_blif_rejects_live_undriven_logic()
    test_blif_prunes_dead_latch_logic()
    test_blif_rejects_requested_latch_output()
    test_blif_rejects_latch_output_dependency()
    test_blif_subckt_flattening()
    test_blif_same_names_are_circuit_local()
    test_blif_input_mapping()
    test_blif_output_mapping()


def test_fast_lut_vs_configurable_lut2() -> None:
    """Check a fast XOR2 LUT target against a configurable LUT2."""
    target = Circuit.lut(name="xor2_target", inputs=["A", "B"], init=0x6, output="Y")

    cand = Circuit("cand")
    a, b = cand.inputs("A", "B")
    y = cand.lut([a, b], name="L0")
    cand.output("Y", y)

    result = Equiv(target, cand).match_inputs_by_name().symbolic_config(cand).solve()
    assert result.sat
    assert result.lut_init(cand, "L0") == 0x6


def test_func_truth_table_default_symbolic_config() -> None:
    """Check automatic Func truth-table generation and default symbolic config."""
    target = Circuit.truth_table(
        name="xor2_target",
        inputs=["A", "B"],
        outputs={"Y": Func.xor("A", "B")},
    )
    cand = Circuit("cand")
    a, b = cand.inputs("A", "B")
    y = cand.lut([a, b], name="L0")
    cand.output("Y", y)
    result = Equiv.check(target, cand).match_inputs_by_name().solve()
    assert result.sat
    assert result.lut_init(cand, "L0") == 0x6


def test_truth_block_full_adder() -> None:
    """Check multi-output fixed truth blocks."""
    target = Circuit.truth_table(
        name="fa_target",
        inputs=["A", "B", "Cin"],
        outputs={
            "SUM": Func.expr(lambda A, B, Cin: A ^ B ^ Cin),
            "COUT": Func.expr(lambda A, B, Cin: (A & B) | (A & Cin) | (B & Cin)),
        },
    )
    cand = Circuit("fa_block")
    a, b, cin = cand.inputs("A", "B", "Cin")
    sum_, cout = cand.truth_block(
        name="FA",
        inputs=[a, b, cin],
        outputs={
            "SUM": Func.expr(lambda A, B, Cin: A ^ B ^ Cin),
            "COUT": Func.expr(lambda A, B, Cin: (A & B) | (A & Cin) | (B & Cin)),
        },
    )
    cand.output("SUM", sum_)
    cand.output("COUT", cout)
    result = Equiv(target, cand).match_inputs_by_name().solve()
    assert result.sat


def test_full_adder_two_manual_lut3() -> None:
    """Check that a full adder fits in two manually routed LUT3s."""
    target = _full_adder_target()
    cand = Circuit("two_lut3_fa")
    a, b, cin = cand.inputs("A", "B", "Cin")
    pool = [a, b, cin]
    sum_ = cand.routed_lut("SUM_LUT", k=3, candidates=pool)
    cout = cand.routed_lut("COUT_LUT", k=3, candidates=pool)
    cand.output("SUM", sum_)
    cand.output("COUT", cout)

    result = Equiv.check(target, cand).match_inputs_by_name().solve()
    assert result.sat
    assert result.config_for(cand).lut_bits("SUM_LUT")
    assert result.config_for(cand).lut_bits("COUT_LUT")


def test_full_adder_two_lut3_network() -> None:
    """Check that lut_network can express a two-LUT3 full adder."""
    target = _full_adder_target()
    cand = Circuit("two_lut3_network_fa")
    a, b, cin = cand.inputs("A", "B", "Cin")
    sum_, cout = cand.lut_network(
        name="FA",
        inputs=[a, b, cin],
        lut_sizes=[3, 3],
        outputs=2,
        allow_routes=True,
    )
    cand.output("SUM", sum_)
    cand.output("COUT", cout)

    result = Equiv.check(target, cand).match_inputs_by_name().solve()
    assert result.sat
    assert result.config_for(cand).lut_bits("FA_LUT0")
    assert result.config_for(cand).lut_bits("FA_LUT1")


def test_builder_helpers() -> None:
    """Check mux tree and reduction helpers."""
    target = Circuit.truth_table(
        name="target",
        inputs=["A", "B", "C", "S"],
        outputs={
            "Y": Func.mux("S", Func.xor("A", "B", "C"), Func.or_("A", "B")),
        },
    )
    cand = Circuit("helpers")
    a, b, c, s = cand.inputs("A", "B", "C", "S")
    parity = cand.reduce_xor([a, b, c], name="parity")
    any_ab = cand.reduce_or([a, b], name="any_ab")
    y = cand.mux_tree([any_ab, parity], [s], name="sel")
    cand.output("Y", y)
    result = Equiv(target, cand).match_inputs_by_name().solve()
    assert result.sat


def test_configurable_vs_configurable_fixed_left() -> None:
    """Check fixed-left configurable circuit synthesis."""
    left = Circuit("left")
    la, lb = left.inputs("A", "B")
    ly = left.lut([la, lb], name="L0")
    left.output("Y", ly)

    right = Circuit("right")
    ra, rb = right.inputs("A", "B")
    ry = right.lut([ra, rb], name="L0")
    right.output("Y", ry)

    cfg_left = ConfigSpec.fixed_lut("c1", "L0", k=2, init=0x6)
    result = (
        Equiv(left, right)
        .match_inputs_by_name()
        .fix_config(left, cfg_left)
        .symbolic_config(right)
        .solve()
    )
    assert result.sat
    assert result.lut_init(right, "L0") == 0x6


def test_fix_pin_and_pinmap() -> None:
    """Check routed LUT pin fixing and decoded pin maps."""
    left = Circuit("left")
    a, b = left.inputs("A", "B")
    yl = left.routed_lut("L0", k=2, candidates=[a, b])
    left.output("Y", yl)

    right = Circuit("right")
    a, b = right.inputs("A", "B")
    yr = right.routed_lut("R0", k=2, candidates=[a, b])
    right.output("Y", yr)

    result = (
        Equiv(left, right)
        .match_inputs_by_name()
        .fix(left, lut={"L0": 0x6}, pins={"L0": ["A", "B"]})
        .symbolic_all(right)
        .solve()
    )
    assert result.sat
    assert result.pinmap(left, "L0") == {"a0": "A", "a1": "B"}


def test_circuit_local_inputs_do_not_match_by_default() -> None:
    """Check that same-named inputs are circuit-local unless explicitly mapped."""
    target = Circuit.truth_table(
        name="identity_target",
        inputs=["A"],
        outputs={"Y": Func.var("A")},
    )
    cand = Circuit("identity_candidate")
    a = cand.input("A")
    cand.output("Y", a)

    local_result = Equiv.check(target, cand).solve()
    assert not local_result.sat

    matched_result = Equiv.check(target, cand).match_inputs_by_name().solve()
    assert matched_result.sat
    assert matched_result.input_mapping(cand) == {"A": "A"}
    assert matched_result.input_mapping(cand, scoped=True) == {"c2/A": "c1/A"}


def test_map_inputs_custom_ports() -> None:
    """Check explicit fixed input mapping with different port names."""
    target = Circuit.truth_table(
        name="target",
        inputs=["A", "B"],
        outputs={"Y": Func.expr(lambda A, B: A and not B)},
    )
    cand = Circuit("custom_ports")
    i0, i1 = cand.inputs("I0", "I1")
    y = cand.and_(i0, cand.not_(i1, name="not_i1"), name="and_i0_not_i1")
    cand.output("Y", y)

    result = Equiv.check(target, cand).map_inputs(cand, {"I0": "A", "I1": "B"}).solve()

    assert result.sat
    assert result.input_mapping(cand) == {"I0": "A", "I1": "B"}
    assert result.input_mapping(cand, scoped=True) == {
        "c2/I0": "c1/A",
        "c2/I1": "c1/B",
    }


def test_route_inputs_lut_with_extra_input() -> None:
    """Check virtual input routes with reuse and a don't-care LUT input."""
    target = Circuit.truth_table(
        name="xor2_target",
        inputs=["A", "B"],
        outputs={"Y": Func.xor("A", "B")},
    )
    cand = Circuit("mapped_lut3")
    i0, i1, i2 = cand.inputs("I0", "I1", "I2")
    y = cand.lut([i0, i1, i2], name="LUT3")
    cand.output("Y", y)

    result = (
        Equiv.check(target, cand)
        .route_inputs(
            cand,
            pool=["A", "B"],
            inputs=["I0", "I1", "I2"],
            allow_reuse=True,
            allow_constants=False,
        )
        .solve()
    )

    assert result.sat
    mapping = result.input_mapping(cand)
    assert set(mapping) == {"I0", "I1", "I2"}
    assert set(mapping.values()) <= {"A", "B"}
    assert result.config_for(cand).lut_bits("LUT3")


def test_route_inputs_injective_mapping() -> None:
    """Check virtual input routes with reuse disabled.

    Raises
    ------
    AssertionError
        If the solved mapping is not injective.
    """
    target = Circuit.truth_table(
        name="xor2_target",
        inputs=["A", "B"],
        outputs={"Y": Func.xor("A", "B")},
    )
    cand = Circuit("mapped_lut2")
    i0, i1 = cand.inputs("I0", "I1")
    y = cand.lut([i0, i1], name="LUT2")
    cand.output("Y", y)

    result = (
        Equiv.check(target, cand)
        .route_inputs(
            cand,
            pool=["A", "B"],
            allow_reuse=False,
        )
        .solve()
    )

    assert result.sat
    mapping = result.input_mapping(cand)
    assert set(mapping) == {"I0", "I1"}
    assert set(mapping.values()) == {"A", "B"}

    oversized = Circuit("oversized")
    oversized.inputs("I0", "I1", "I2")
    try:
        Equiv.check(target, oversized).route_inputs(
            oversized,
            pool=["A", "B"],
            allow_reuse=False,
        )
    except ValueError:
        pass
    else:
        raise AssertionError("expected impossible injective route_inputs to fail")


def test_route_outputs_single_target() -> None:
    """Check one target output can select among several candidate outputs."""
    target = Circuit.truth_table(
        name="xor_target",
        inputs=["A", "B"],
        outputs={"Y": Func.xor("A", "B")},
    )
    cand = Circuit("multi_output")
    a, b = cand.inputs("A", "B")
    cand.output("O0", cand.and_(a, b, name="wrong_and"))
    cand.output("O1", cand.xor(a, b, name="right_xor"))
    cand.output("O2", cand.or_(a, b, name="wrong_or"))

    result = (
        Equiv.check(target, cand)
        .match_inputs_by_name()
        .route_outputs(cand, {"Y": ["O0", "O1", "O2"]})
        .solve()
    )

    assert result.sat
    assert result.output_mapping(cand) == {"Y": "O1"}
    assert result.output_mapping(cand, scoped=True) == {"c1/Y": "c2/O1"}


def test_route_outputs_multi_target_no_reuse() -> None:
    """Check several target outputs can select distinct candidate outputs."""
    target = _full_adder_target()
    cand = Circuit("multi_output_fa")
    a, b, cin = cand.inputs("A", "B", "Cin")
    sum_ = cand.reduce_xor([a, b, cin], name="sum")
    ab = cand.and_(a, b, name="ab")
    ac = cand.and_(a, cin, name="ac")
    bc = cand.and_(b, cin, name="bc")
    cout = cand.reduce_or([ab, ac, bc], name="cout")
    cand.output("O0", cout)
    cand.output("O1", sum_)
    cand.output("O2", cand.or_(a, b, name="junk"))

    result = (
        Equiv.check(target, cand)
        .match_inputs_by_name()
        .route_outputs(
            cand,
            {
                "SUM": ["O0", "O1", "O2"],
                "COUT": ["O0", "O1", "O2"],
            },
            allow_reuse=False,
        )
        .solve()
    )

    assert result.sat
    assert result.output_mapping(cand) == {"SUM": "O1", "COUT": "O0"}


def test_route_inputs_and_outputs_together() -> None:
    """Check virtual input and output routing in one equivalence solve."""
    target = Circuit.truth_table(
        name="and_not_spec",
        inputs=["A", "B"],
        outputs={"Y": Func.expr(lambda A, B: A and not B)},
    )
    cand = Circuit("routed_in_and_out")
    i, j, k = cand.inputs("I", "J", "K")
    cand.output("O0", cand.and_(i, j, name="wrong_and"))
    cand.output("O1", cand.and_(i, cand.not_(j, name="not_j"), name="right"))
    cand.output("O2", cand.xor(i, k, name="wrong_xor"))

    result = (
        Equiv.check(target, cand)
        .route_inputs(
            cand,
            pool=["A", "B"],
            inputs=["I", "J", "K"],
            allow_reuse=True,
            allow_constants=False,
        )
        .route_outputs(cand, {"Y": ["O0", "O1", "O2"]})
        .solve()
    )

    assert result.sat
    assert result.input_mapping(cand)["I"] == "A"
    assert result.input_mapping(cand)["J"] == "B"
    assert result.output_mapping(cand) == {"Y": "O1"}


def test_route_inputs_lut6_mux4_to_two_lut5_hard_mux() -> None:
    """Check a LUT6 MUX4 mapped onto two LUT5s with a hard mux."""
    c1 = Circuit.truth_table(
        name="mux4_lut6_spec",
        inputs=["D0", "D1", "D2", "D3", "S0", "S1"],
        outputs={
            "Y": Func.mux_indexed(
                data=["D0", "D1", "D2", "D3"],
                select=["S0", "S1"],
            )
        },
    )

    c2 = Circuit("two_lut5_hard_mux")
    i0, i1, i2, i3, p0, p2, s = c2.inputs(
        "I0",
        "I1",
        "I2",
        "I3",
        "P0",
        "P2",
        "S",
    )

    lo = c2.lut([i0, i1, i2, i3, p0], name="LUT5_LO")
    hi = c2.lut([i0, i1, i2, i3, p2], name="LUT5_HI")
    y = c2.mux(sel=s, d0=lo, d1=hi, name="MUX2")
    c2.output("Y", y)

    result = (
        Equiv.check(c1, c2)
        .route_inputs(
            c2,
            pool=["D0", "D1", "D2", "D3", "S0", "S1"],
            inputs=["I0", "I1", "I2", "I3", "P0", "P2", "S"],
            allow_reuse=True,
            allow_constants=False,
        )
        .solve()
    )

    assert result.sat
    mapping = result.input_mapping(c2)
    assert set(mapping) == {"I0", "I1", "I2", "I3", "P0", "P2", "S"}
    assert set(mapping.values()) <= {"D0", "D1", "D2", "D3", "S0", "S1"}
    assert result.config_for(c2).lut_bits("LUT5_LO")
    assert result.config_for(c2).lut_bits("LUT5_HI")


def test_blif_flut6_implements_mux4_lut6() -> None:
    """Check the FLUT6 BLIF can implement a LUT6 MUX4."""
    c1 = Circuit.truth_table(
        name="mux4_lut6_spec",
        inputs=["D0", "D1", "D2", "D3", "S0", "S1"],
        outputs={
            "X": Func.mux_indexed(
                data=["D0", "D1", "D2", "D3"],
                select=["S0", "S1"],
            )
        },
    )

    c2 = Circuit.from_blif(
        Path(__file__).with_name("FLUT6.blif"),
        top="FRACTURABLE_LUT6",
        inputs=["I0", "I1", "I2", "I3", "P0", "P1", "S"],
        config_prefixes=["INIT"],
        outputs=["O5_0", "O5_1", "O6"],
    )

    result = (
        Equiv.check(c1, c2)
        .route_inputs(
            c2,
            pool=["D0", "D1", "D2", "D3", "S0", "S1"],
            inputs=["I0", "I1", "I2", "I3", "P0", "P1", "S"],
            allow_reuse=True,
            allow_constants=False,
        )
        .route_outputs(
            c2,
            {"X": ["O5_0", "O5_1", "O6"]},
            allow_reuse=False,
        )
        .solve()
    )

    assert result.sat
    mapping = result.input_mapping(c2)
    assert set(mapping) == {"I0", "I1", "I2", "I3", "P0", "P1", "S"}
    assert set(mapping.values()) <= {"D0", "D1", "D2", "D3", "S0", "S1"}
    config = result.config_for(c2)
    assert all(
        config.external_value(f"INIT0[{index}]") is not None for index in range(32)
    )
    assert all(
        config.external_value(f"INIT1[{index}]") is not None for index in range(32)
    )

    cfg = result.config_for(c2)

    print("C2 input mapping")  # noqa: T201
    for dst, src in result.input_mapping(c2, scoped=True).items():
        print(f"  {dst} <- {src}")  # noqa: T201

    print("C2 output mapping")  # noqa: T201
    for dst, src in result.output_mapping(c2, scoped=True).items():
        print(f"  {dst} <- {src}")  # noqa: T201

    print("C2 top config ports")  # noqa: T201
    for name in c2.config_names():
        value = cfg.external_value(name)
        print(f"  c2/{name} = {int(bool(value))}")  # noqa: T201


def test_blif_flut51p2ps_implements_mux4_lut6() -> None:
    """Check the FLUT6 BLIF can implement a LUT6 MUX4."""
    c1 = Circuit.truth_table(
        name="mux4_lut6_spec",
        inputs=["D0", "D1", "D2", "D3", "S0", "S1"],
        outputs={
            "X": Func.mux_indexed(
                data=["D0", "D1", "D2", "D3"],
                select=["S0", "S1"],
            )
        },
    )

    c2 = Circuit.from_blif(
        Path(__file__).with_name("FLUT5_1P_2PS.blif"),
        top="LUT4x2_V2_frame_config",
        inputs=["I0", "I1", "I2", "A0", "B0", "S", "Ci"],
        config_prefixes=["ConfigBits"],
        outputs=["O0", "O1", "Co"],
    )

    result = (
        Equiv.check(c1, c2)
        .route_inputs(
            c2,
            pool=["D0", "D1", "D2", "D3", "S0", "S1"],
            inputs=["I0", "I1", "I2", "A0", "B0", "S", "Ci"],
            allow_reuse=True,
            allow_constants=False,
        )
        .route_outputs(
            c2,
            {"X": ["O0", "O1", "Co"]},
            allow_reuse=False,
        )
        .solve()
    )

    assert result.sat
    mapping = result.input_mapping(c2)
    assert set(mapping) == {"I0", "I1", "I2", "A0", "B0", "S", "Ci"}
    assert set(mapping.values()) <= {"D0", "D1", "D2", "D3", "S0", "S1"}

    cfg = result.config_for(c2)

    print("C2 input mapping")  # noqa: T201
    for dst, src in result.input_mapping(c2, scoped=True).items():
        print(f"  {dst} <- {src}")  # noqa: T201

    print("C2 output mapping")  # noqa: T201
    for dst, src in result.output_mapping(c2, scoped=True).items():
        print(f"  {dst} <- {src}")  # noqa: T201

    print("C2 top config ports")  # noqa: T201
    for name in c2.config_names():
        value = cfg.external_value(name)
        print(f"  c2/{name} = {int(bool(value))}")  # noqa: T201


def test_blif_flut51p2ps_implements_xor6() -> None:
    """Check the FLUT6 BLIF can implement a XOR6."""
    c1 = Circuit.truth_table(
        name="xor6_spec",
        inputs=["D0", "D1", "D2", "D3", "D4", "D5"],
        outputs={
            "X": Func.xor("D0", "D1", "D2", "D3", "D4", "D5"),
        },
    )

    c2 = Circuit.from_blif(
        Path(__file__).with_name("FLUT5_1P_2PS.blif"),
        top="LUT4x2_V2_frame_config",
        inputs=["I0", "I1", "I2", "A0", "B0", "S", "Ci"],
        config_prefixes=["ConfigBits"],
        outputs=["O0", "O1", "Co"],
    )

    result = (
        Equiv.check(c1, c2)
        .route_inputs(
            c2,
            pool=["D0", "D1", "D2", "D3", "D4", "D5"],
            inputs=["I0", "I1", "I2", "A0", "B0", "S", "Ci"],
            allow_reuse=True,
            allow_constants=False,
        )
        .route_outputs(
            c2,
            {"X": ["O0", "O1", "Co"]},
            allow_reuse=False,
        )
        .solve()
    )

    assert result.sat
    mapping = result.input_mapping(c2)
    assert set(mapping) == {"I0", "I1", "I2", "A0", "B0", "S", "Ci"}
    assert set(mapping.values()) <= {"D0", "D1", "D2", "D3", "D4", "D5"}

    cfg = result.config_for(c2)

    print("C2 input mapping")  # noqa: T201
    for dst, src in result.input_mapping(c2, scoped=True).items():
        print(f"  {dst} <- {src}")  # noqa: T201

    print("C2 output mapping")  # noqa: T201
    for dst, src in result.output_mapping(c2, scoped=True).items():
        print(f"  {dst} <- {src}")  # noqa: T201

    print("C2 top config ports")  # noqa: T201
    for name in c2.config_names():
        value = cfg.external_value(name)
        print(f"  c2/{name} = {int(bool(value))}")  # noqa: T201


def test_blif_flut51p2ps_implements_LUT() -> None:
    """Check the FLUT6 BLIF can implement a LUT."""
    c1 = Circuit.fast_lut(
        name="lut6_spec",
        init=0x6996966996696996,
        inputs=["A0", "A1", "A2", "A3", "A4", "A5"],
        output="X",
    )

    c2 = Circuit.from_blif(
        Path(__file__).with_name("FLUT5_1P_2PS.blif"),
        top="LUT4x2_V2_frame_config",
        inputs=["I0", "I1", "I2", "A0", "B0", "S", "Ci"],
        config_prefixes=["ConfigBits"],
        outputs=["O0", "O1", "Co"],
    )

    result = (
        Equiv.check(c1, c2)
        .route_inputs(
            c2,
            pool=["A0", "A1", "A2", "A3", "A4", "A5"],
            inputs=["I0", "I1", "I2", "A0", "B0", "S", "Ci"],
            allow_reuse=True,
            allow_constants=False,
        )
        .route_outputs(
            c2,
            {"X": ["O0", "O1", "Co"]},
            allow_reuse=False,
        )
        .solve()
    )

    assert result.sat
    mapping = result.input_mapping(c2)
    assert set(mapping) == {"I0", "I1", "I2", "A0", "B0", "S", "Ci"}
    assert set(mapping.values()) <= {"A0", "A1", "A2", "A3", "A4", "A5"}

    cfg = result.config_for(c2)

    print("C2 input mapping")  # noqa: T201
    for dst, src in result.input_mapping(c2, scoped=True).items():
        print(f"  {dst} <- {src}")  # noqa: T201

    print("C2 output mapping")  # noqa: T201
    for dst, src in result.output_mapping(c2, scoped=True).items():
        print(f"  {dst} <- {src}")  # noqa: T201

    print("C2 top config ports")  # noqa: T201
    for name in c2.config_names():
        value = cfg.external_value(name)
        print(f"  c2/{name} = {int(bool(value))}")  # noqa: T201


def test_routed_lut_network_mux4() -> None:
    """Check a routed two-LUT4 network against a MUX4 target."""
    target = Circuit.lut(
        name="mux4_target",
        inputs=["D0", "D1", "D2", "D3", "S0", "S1"],
        init=_mux4_init(),
        output="Y",
    )

    cand = Circuit("two_lut4")
    d0, d1, d2, d3, s0, s1 = cand.inputs("D0", "D1", "D2", "D3", "S0", "S1")
    pool1 = [d0, d1, d2, d3, s0, s1]
    t = cand.routed_lut("LUT0", k=4, candidates=pool1)
    y = cand.routed_lut("LUT1", k=4, candidates=[d0, d1, d2, d3, s0, s1, t])
    cand.output("Y", y)

    result = Equiv(target, cand).match_inputs_by_name().symbolic_config(cand).solve()
    assert result.sat
    assert result.config_for(cand).lut_bits("LUT0")
    assert result.config_for(cand).lut_bits("LUT1")


def test_blif_names_import() -> None:
    """Check BLIF ``.names`` import."""
    with TemporaryDirectory() as tmp:
        path = Path(tmp) / "xor.blif"
        path.write_text(
            "\n".join(
                [
                    ".model top",
                    ".inputs A B",
                    ".outputs Y",
                    ".names A B Y",
                    "10 1",
                    "01 1",
                    ".end",
                ]
            )
        )
        imported = Circuit.from_blif(path, inputs=["A", "B"], outputs=["Y"])
        target = Circuit.lut(name="xor2", inputs=["A", "B"], init=0x6, output="Y")
        result = Equiv(target, imported).match_inputs_by_name().solve()
        assert result.sat


def test_blif_out_of_order_names_import() -> None:
    """Check BLIF import sorts late internal drivers before users."""
    with TemporaryDirectory() as tmp:
        path = Path(tmp) / "out_of_order_and.blif"
        path.write_text(
            "\n".join(
                [
                    ".model top",
                    ".inputs A B",
                    ".outputs Y",
                    ".names n1 B Y",
                    "11 1",
                    ".names A n1",
                    "1 1",
                    ".end",
                ]
            )
        )
        imported = Circuit.from_blif(path, inputs=["A", "B"], outputs=["Y"])
        target = Circuit.truth_table(
            name="and2",
            inputs=["A", "B"],
            outputs={"Y": Func.and_("A", "B")},
        )
        result = Equiv.check(target, imported).match_inputs_by_name().solve()
        assert result.sat


def test_blif_out_of_order_subckt_flattening() -> None:
    """Check flattened subckt drivers can appear after their users."""
    with TemporaryDirectory() as tmp:
        path = Path(tmp) / "out_of_order_subckt.blif"
        path.write_text(
            "\n".join(
                [
                    ".model top",
                    ".inputs A B",
                    ".outputs Y",
                    ".names N B Y",
                    "11 1",
                    ".subckt BUF I=A O=N",
                    ".end",
                    ".model BUF",
                    ".inputs I",
                    ".outputs O",
                    ".names I O",
                    "1 1",
                    ".end",
                ]
            )
        )
        imported = Circuit.from_blif(path, top="top", inputs=["A", "B"], outputs=["Y"])
        target = Circuit.truth_table(
            name="and2",
            inputs=["A", "B"],
            outputs={"Y": Func.and_("A", "B")},
        )
        result = Equiv.check(target, imported).match_inputs_by_name().solve()
        assert result.sat


def test_blif_prunes_dead_undriven_logic() -> None:
    """Check BLIF import drops dead logic with undriven sources."""
    with TemporaryDirectory() as tmp:
        path = Path(tmp) / "dead_undriven.blif"
        path.write_text(
            "\n".join(
                [
                    ".model top",
                    ".inputs A",
                    ".outputs Y",
                    ".names A Y",
                    "1 1",
                    ".names floating dead",
                    "1 1",
                    ".end",
                ]
            )
        )
        imported = Circuit.from_blif(path, inputs=["A"], outputs=["Y"])
        target = Circuit.truth_table(
            name="identity",
            inputs=["A"],
            outputs={"Y": Func.var("A")},
        )
        result = Equiv.check(target, imported).match_inputs_by_name().solve()
        assert result.sat
        assert imported.output_names() == ["Y"]


def test_blif_rejects_live_undriven_logic() -> None:
    """Check BLIF import still rejects undriven logic in the output cone.

    Raises
    ------
    AssertionError
        If a live undriven BLIF net is silently accepted.
    """
    with TemporaryDirectory() as tmp:
        path = Path(tmp) / "live_undriven.blif"
        path.write_text(
            "\n".join(
                [
                    ".model top",
                    ".inputs A",
                    ".outputs Y",
                    ".names floating Y",
                    "1 1",
                    ".end",
                ]
            )
        )
        error_message = ""
        try:
            Circuit.from_blif(path, inputs=["A"], outputs=["Y"])
        except ValueError as exc:
            error_message = str(exc)
        if not error_message:
            raise AssertionError("expected live undriven BLIF logic to fail")
        assert "floating" in error_message


def test_blif_prunes_dead_latch_logic() -> None:
    """Check BLIF import accepts latches outside the requested output cone."""
    with TemporaryDirectory() as tmp:
        path = Path(tmp) / "dead_latch.blif"
        path.write_text(
            "\n".join(
                [
                    ".model top",
                    ".inputs A CLK",
                    ".outputs Y Q",
                    ".names A Y",
                    "1 1",
                    ".names A next_q",
                    "0 1",
                    ".latch next_q Q re CLK 2",
                    ".end",
                ]
            )
        )
        imported = Circuit.from_blif(path, inputs=["A"], outputs=["Y"])
        target = Circuit.truth_table(
            name="identity",
            inputs=["A"],
            outputs={"Y": Func.var("A")},
        )
        result = Equiv.check(target, imported).match_inputs_by_name().solve()
        assert result.sat


def test_blif_rejects_requested_latch_output() -> None:
    """Check BLIF import rejects requested sequential outputs.

    Raises
    ------
    AssertionError
        If a requested latch output is silently accepted.
    """
    with TemporaryDirectory() as tmp:
        path = Path(tmp) / "requested_latch.blif"
        path.write_text(
            "\n".join(
                [
                    ".model top",
                    ".inputs A CLK",
                    ".outputs Q",
                    ".names A next_q",
                    "1 1",
                    ".latch next_q Q re CLK 2",
                    ".end",
                ]
            )
        )
        error_message = ""
        try:
            Circuit.from_blif(path, inputs=["A"], outputs=["Q"])
        except ValueError as exc:
            error_message = str(exc)
        if not error_message:
            raise AssertionError("expected requested BLIF latch output to fail")
        assert "sequential BLIF is not supported" in error_message


def test_blif_rejects_latch_output_dependency() -> None:
    """Check BLIF import rejects combinational cones fed by latches.

    Raises
    ------
    AssertionError
        If a live latch dependency is silently accepted.
    """
    with TemporaryDirectory() as tmp:
        path = Path(tmp) / "live_latch_dependency.blif"
        path.write_text(
            "\n".join(
                [
                    ".model top",
                    ".inputs A CLK",
                    ".outputs Y",
                    ".names A next_q",
                    "1 1",
                    ".latch next_q Q re CLK 2",
                    ".names Q Y",
                    "1 1",
                    ".end",
                ]
            )
        )
        error_message = ""
        try:
            Circuit.from_blif(path, inputs=["A"], outputs=["Y"])
        except ValueError as exc:
            error_message = str(exc)
        if not error_message:
            raise AssertionError("expected live BLIF latch dependency to fail")
        assert "latch output 'Q' is live" in error_message


def test_blif_subckt_flattening() -> None:
    """Check BLIF ``.subckt`` flattening."""
    with TemporaryDirectory() as tmp:
        path = Path(tmp) / "subckt.blif"
        path.write_text(
            "\n".join(
                [
                    ".model top",
                    ".inputs A B",
                    ".outputs Y",
                    ".subckt XOR2 I0=A I1=B O=Y",
                    ".end",
                    ".model XOR2",
                    ".inputs I0 I1",
                    ".outputs O",
                    ".names I0 I1 O",
                    "10 1",
                    "01 1",
                    ".end",
                ]
            )
        )
        imported = Circuit.from_blif(path, top="top", inputs=["A", "B"], outputs=["Y"])
        target = Circuit.lut(name="xor2", inputs=["A", "B"], init=0x6, output="Y")
        result = Equiv(target, imported).match_inputs_by_name().solve()
        assert result.sat


def test_blif_same_names_are_circuit_local() -> None:
    """Check that BLIF inputs with same names are local unless matched."""
    with TemporaryDirectory() as tmp:
        path = Path(tmp) / "identity.blif"
        path.write_text(
            "\n".join(
                [
                    ".model top",
                    ".inputs A",
                    ".outputs Y",
                    ".names A Y",
                    "1 1",
                    ".end",
                ]
            )
        )
        imported = Circuit.from_blif(path, inputs=["A"], outputs=["Y"])
        target = Circuit.truth_table(
            name="identity",
            inputs=["A"],
            outputs={"Y": Func.var("A")},
        )

        local_result = Equiv.check(target, imported).solve()
        assert not local_result.sat

        matched_result = Equiv.check(target, imported).match_inputs_by_name().solve()
        assert matched_result.sat


def test_blif_input_mapping() -> None:
    """Check virtual input mapping in front of an imported BLIF circuit."""
    with TemporaryDirectory() as tmp:
        path = Path(tmp) / "xor_renamed.blif"
        path.write_text(
            "\n".join(
                [
                    ".model top",
                    ".inputs X Y",
                    ".outputs Z",
                    ".names X Y Z",
                    "10 1",
                    "01 1",
                    ".end",
                ]
            )
        )
        imported = Circuit.from_blif(path, inputs=["X", "Y"], outputs=["Z"])
        target = Circuit.truth_table(
            name="xor2",
            inputs=["A", "B"],
            outputs={"Z": Func.xor("A", "B")},
        )
        result = (
            Equiv.check(target, imported)
            .route_inputs(
                imported,
                pool=["A", "B"],
                allow_reuse=False,
            )
            .solve()
        )

        assert result.sat
        mapping = result.input_mapping(imported)
        assert set(mapping) == {"X", "Y"}
        assert set(mapping.values()) == {"A", "B"}


def test_blif_output_mapping() -> None:
    """Check virtual output mapping in front of an imported BLIF circuit."""
    with TemporaryDirectory() as tmp:
        path = Path(tmp) / "multi_out.blif"
        path.write_text(
            "\n".join(
                [
                    ".model top",
                    ".inputs X",
                    ".outputs Z0 Z1",
                    ".names X Z0",
                    "0 1",
                    ".names X Z1",
                    "1 1",
                    ".end",
                ]
            )
        )
        imported = Circuit.from_blif(path, inputs=["X"], outputs=["Z0", "Z1"])
        target = Circuit.truth_table(
            name="identity",
            inputs=["A"],
            outputs={"Y": Func.var("A")},
        )
        result = (
            Equiv.check(target, imported)
            .map_inputs(imported, {"X": "A"})
            .route_outputs(imported, {"Y": ["Z0", "Z1"]})
            .solve()
        )

        assert result.sat
        assert result.output_mapping(imported) == {"Y": "Z1"}


def _mux4_init() -> int:
    """Build the LSB-first INIT for ``D[S]``.

    Returns
    -------
    int
        INIT for inputs ``D0,D1,D2,D3,S0,S1``.
    """
    init = 0
    for index in range(64):
        d0 = bool((index >> 0) & 1)
        d1 = bool((index >> 1) & 1)
        d2 = bool((index >> 2) & 1)
        d3 = bool((index >> 3) & 1)
        s0 = bool((index >> 4) & 1)
        s1 = bool((index >> 5) & 1)
        selected = [d0, d1, d2, d3][int(s0) | (int(s1) << 1)]
        if selected:
            init |= 1 << index
    return init


def _full_adder_target() -> TruthTableSpec:
    """Build a fast full-adder target.

    Returns
    -------
    TruthTableSpec
        Full-adder truth-table target.
    """
    return Circuit.truth_table(
        name="full_adder_target",
        inputs=["A", "B", "Cin"],
        outputs={
            "SUM": Func.expr(lambda A, B, Cin: A ^ B ^ Cin),
            "COUT": Func.expr(lambda A, B, Cin: (A & B) | (A & Cin) | (B & Cin)),
        },
    )


if __name__ == "__main__":
    run_all_tests()
