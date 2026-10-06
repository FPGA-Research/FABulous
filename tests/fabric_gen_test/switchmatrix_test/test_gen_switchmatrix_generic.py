"""Netlist checks of the switch-matrix muxes for both multiplexer styles.

Each multi-input mux must take `connections[port][k]` on data input `k` and
read its select from the config bits the bitstream spec assigns it: muxes take
consecutive `ConfigBits` slices of `ceil(log2(n))` bits in connection order.
The generated matrix of a default-project tile is elaborated with Yosys, so an
undriven input vector, a reordered input or a shifted select slice all fail.
"""

from collections.abc import Callable

import pytest

from fabulous.fabric_definition.define import SWITCH_MATRIX_CONSTANTS, MultiplexerStyle
from fabulous.fabric_definition.tile import Tile
from fabulous.fabric_generator.code_generator.code_generator import CodeGenerator
from fabulous.fabric_generator.gen_fabric.gen_switchmatrix import genTileSwitchMatrix
from tests.fabric_gen_test.conftest import Netlist, cus_mux_stubs, mux_wiring


@pytest.mark.parametrize("style", [MultiplexerStyle.CUSTOM, MultiplexerStyle.GENERIC])
def test_mux_inputs_and_selects_follow_connections(
    style: MultiplexerStyle,
    switch_matrix_tile: Tile,
    code_generator_factory: Callable[[str, str], CodeGenerator],
    elaborate: Callable[..., Netlist],
) -> None:
    """Every mux selects `connections[port][k]` with its own config-bit slice."""
    writer = code_generator_factory(".v", f"{switch_matrix_tile.name}_switch_matrix")
    genTileSwitchMatrix(writer, switch_matrix_tile, False, multiplexer_style=style)
    net = elaborate(writer.outFileName.read_text() + cus_mux_stubs())

    def source_net(name: str) -> int | str:
        if name in SWITCH_MATRIX_CONSTANTS:
            return "0" if name.startswith("GND") else "1"
        (bit,) = net.port_net(name)
        return bit

    config_bits = net.port_net("ConfigBits")
    config_bits_n = net.port_net("ConfigBits_N")
    position = 0
    checked = 0
    for port, sources in switch_matrix_tile.switch_matrix.connections.items():
        if len(sources) < 2:
            continue
        width = (len(sources) - 1).bit_length()
        wiring = mux_wiring(net, port)

        expected = [source_net(s) for s in sources]
        # A custom mux pads its unused data inputs with GND0.
        padding = ["0"] * (len(wiring.inputs) - len(expected))
        assert wiring.inputs == expected + padding, port
        assert wiring.selects == config_bits[position : position + width], port
        if wiring.selects_n:
            assert wiring.selects_n == config_bits_n[position : position + width]

        position += width
        checked += 1

    assert checked, "the tile has no multi-input mux to check"
    assert position == len(config_bits)
