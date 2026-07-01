"""Tests for the generic-style switch-matrix multiplexer path.

A generic mux selects a source by indexing the `{portName}_input` vector with
the relevant `ConfigBits`. That vector must be driven from the connection list
(reversed, so `input[i]` is `connections[i]`); otherwise the mux indexes an
undriven wire. These tests run the real generation path over a default-project
tile and assert every declared input vector is driven.
"""

import re
from collections.abc import Callable

from fabulous.fabric_definition.define import MultiplexerStyle
from fabulous.fabric_definition.tile import Tile
from fabulous.fabric_generator.code_generator.code_generator import CodeGenerator
from fabulous.fabric_generator.gen_fabric.gen_switchmatrix import genTileSwitchMatrix

_INPUT_DECL = re.compile(r"\b(\w+)_input\s*;")
_INPUT_ASSIGN = re.compile(r"assign\s+(\w+)_input\s*=")


def _generate(
    tile: Tile,
    writer: CodeGenerator,
    style: MultiplexerStyle,
) -> str:
    """Generate the switch-matrix HDL for `tile` and return it."""
    genTileSwitchMatrix(writer, tile, False, multiplexer_style=style)
    return writer.outFileName.read_text()


class TestGenericMultiplexerInputVector:
    """Generic-style muxes must drive every declared `{portName}_input` vector."""

    def test_every_generic_input_vector_is_driven(
        self,
        switch_matrix_tile: Tile,
        code_generator_factory: Callable[[str, str], CodeGenerator],
    ) -> None:
        """Each `_input` vector declared for a generic mux is also assigned.

        The undriven-input regression declared the vector but never assigned
        it, leaving the mux indexing a floating wire. Every declared vector
        must have a matching `assign`.
        """
        hdl = _generate(
            switch_matrix_tile,
            code_generator_factory(".v", "generic"),
            MultiplexerStyle.GENERIC,
        )

        declared = set(_INPUT_DECL.findall(hdl))
        assigned = set(_INPUT_ASSIGN.findall(hdl))
        # The tile must actually exercise the mux path, otherwise this is vacuous.
        assert declared, "expected at least one configurable mux in the tile"
        assert declared == assigned, (
            f"input vectors declared but not driven: {sorted(declared - assigned)}"
        )

    def test_generic_matches_custom_input_drive(
        self,
        switch_matrix_tile: Tile,
        code_generator_factory: Callable[[str, str], CodeGenerator],
    ) -> None:
        """Generic and custom styles drive the same set of `_input` vectors.

        The first generation rewrites the `.list` matrix to `.csv` in place;
        the second reads that `.csv`, so both styles see identical connections.
        """
        custom_hdl = _generate(
            switch_matrix_tile,
            code_generator_factory(".v", "custom"),
            MultiplexerStyle.CUSTOM,
        )
        generic_hdl = _generate(
            switch_matrix_tile,
            code_generator_factory(".v", "generic"),
            MultiplexerStyle.GENERIC,
        )

        custom_assigns = set(_INPUT_ASSIGN.findall(custom_hdl))
        generic_assigns = set(_INPUT_ASSIGN.findall(generic_hdl))
        assert custom_assigns
        assert custom_assigns == generic_assigns
