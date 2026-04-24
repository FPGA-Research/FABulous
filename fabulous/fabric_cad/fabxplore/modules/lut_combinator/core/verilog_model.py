"""Verilog behavioral models for LUT combinator architecture cells."""

from dataclasses import dataclass


@dataclass(frozen=True)
class FracLutBehavioralModel:
    """Generate the behavioral Verilog model for a fractional LUT cell.

    The model is shared by the Pyosys pass and equivalence checker so both places
    elaborate the same FRAC LUT semantics.
    """

    name: str
    lut_size: int
    num_shared_inputs: int
    interface_width: int | None = None
    include_equiv_compat_params: bool = False

    def __post_init__(self) -> None:
        """Validate model dimensions."""
        if self.lut_size < 1:
            raise ValueError("lut_size must be >= 1")
        if self.num_shared_inputs < 0 or self.num_shared_inputs > self.lut_size:
            raise ValueError("num_shared_inputs must be in [0, lut_size]")
        if self.interface_width is not None and self.interface_width < self.lut_size:
            raise ValueError("interface_width must be >= lut_size")

    def to_verilog(self) -> str:
        """Return the behavioral model as Verilog source text."""
        return "\n".join(self.to_lines()) + "\n"

    def to_lines(self) -> list[str]:
        """Return the behavioral model as Verilog source lines."""
        k: int = self.lut_size
        s: int = self.num_shared_inputs
        p: int = k - s
        init_width: int = 1 << k
        shared_port_count: int = (
            s if self.interface_width is None else self.interface_width
        )
        side_port_count: int = (
            p if self.interface_width is None else self.interface_width
        )

        shared_ports: list[str] = [f"I{i}" for i in range(shared_port_count)]
        a_ports: list[str] = [f"A{i}" for i in range(side_port_count)]
        b_ports: list[str] = [f"B{i}" for i in range(side_port_count)]
        all_ports: list[str] = shared_ports + a_ports + b_ports + ["S", "O0", "O1"]

        l0_bits: list[str] = [f"I{i}" for i in range(s)] + [f"A{i}" for i in range(p)]
        l1_bits: list[str] = [f"I{i}" for i in range(s)] + [f"B{i}" for i in range(p)]
        l0_cut_bits: list[str] = self._select_as_data_bits("A")
        l1_cut_bits: list[str] = self._select_as_data_bits("B")

        lines: list[str] = [f"module {self.name}({', '.join(all_ports)});"]
        self._append_port_declarations(lines, shared_ports, a_ports, b_ports)
        lines.extend(
            [
                "  input S;",
                "  output O0, O1;",
                '  parameter META_DATA = "";',
                '  parameter L0_CELL_ID = "";',
                '  parameter L1_CELL_ID = "";',
            ]
        )
        if self.include_equiv_compat_params:
            lines.extend(
                [
                    '  parameter F0_CELL_ID = "";',
                    '  parameter F1_CELL_ID = "";',
                ]
            )
        lines.extend(
            [
                "  parameter SELECT_AS_DATA_CAPABLE = 0;",
                "  parameter SELECT_AS_DATA_USED = 0;",
                f"  parameter EFFECTIVE_SHARED_INPUTS = {s};",
                "  parameter CUT_SHARED_INDEX = -1;",
                "  parameter MUX_SELECT_CONFIG = 0;",
            ]
        )
        if self.include_equiv_compat_params:
            lines.append("  parameter [255:0] MAPPED_FROM = 256'b0;")
        lines.extend(
            [
                f"  parameter [{init_width - 1}:0] L0_INIT = {init_width}'b0;",
                f"  parameter [{init_width - 1}:0] L1_INIT = {init_width}'b0;",
            ]
        )
        if self.include_equiv_compat_params:
            lines.extend(
                [
                    f"  parameter [{init_width - 1}:0] F0_INIT = {init_width}'b0;",
                    f"  parameter [{init_width - 1}:0] F1_INIT = {init_width}'b0;",
                ]
            )
        lines.extend(
            [
                f'  parameter LUT_SIZE = "{k}";',
                f'  parameter NUM_SHARED_INPUTS = "{s}";',
                f"  wire [{k - 1}:0] _idx0_normal = {{{self._idx_expr(l0_bits)}}};",
                f"  wire [{k - 1}:0] _idx1_normal = {{{self._idx_expr(l1_bits)}}};",
                f"  wire [{k - 1}:0] _idx0_cut = {{{self._idx_expr(l0_cut_bits)}}};",
                f"  wire [{k - 1}:0] _idx1_cut = {{{self._idx_expr(l1_cut_bits)}}};",
                (
                    f"  wire [{k - 1}:0] _idx0_pair = "
                    "SELECT_AS_DATA_USED ? _idx0_cut : _idx0_normal;"
                ),
                (
                    f"  wire [{k - 1}:0] _idx1_pair = "
                    "SELECT_AS_DATA_USED ? _idx1_cut : _idx1_normal;"
                ),
            ]
        )
        lines.extend(self._logic_lines(init_width))
        lines.append("endmodule")
        return lines

    def _append_port_declarations(
        self,
        lines: list[str],
        shared_ports: list[str],
        a_ports: list[str],
        b_ports: list[str],
    ) -> None:
        """Append input declarations for generated ports."""
        if shared_ports:
            lines.append(f"  input {', '.join(shared_ports)};")
        if a_ports:
            lines.append(f"  input {', '.join(a_ports)};")
        if b_ports:
            lines.append(f"  input {', '.join(b_ports)};")

    def _logic_lines(self, init_width: int) -> list[str]:
        """Return output logic lines for normal or equivalence-compatible models."""
        if not self.include_equiv_compat_params:
            return [
                "  wire _l0_pair = L0_INIT[_idx0_pair];",
                "  wire _l1_pair = L1_INIT[_idx1_pair];",
                (
                    "  assign O0 = SELECT_AS_DATA_USED ? "
                    "(MUX_SELECT_CONFIG ? _l1_pair : _l0_pair) : "
                    "(S ? _l1_pair : _l0_pair);"
                ),
                "  assign O1 = _l1_pair;",
            ]

        idx_full_bits: list[str] = [f"I{i}" for i in range(self.lut_size)]
        return [
            f"  wire [{self.lut_size - 1}:0] _idx_full = "
            f"{{{self._idx_expr(idx_full_bits)}}};",
            f"  wire [{init_width - 1}:0] _i0 = L0_INIT | F0_INIT;",
            f"  wire [{init_width - 1}:0] _i1 = L1_INIT | F1_INIT;",
            "  wire _l0_pair = _i0[_idx0_pair];",
            "  wire _l1_pair = _i1[_idx1_pair];",
            "  wire _l0_full = _i0[_idx_full];",
            "  wire _l1_full = _i1[_idx_full];",
            "  wire _use_full = |MAPPED_FROM;",
            (
                "  assign O0 = _use_full ? (S ? _l1_full : _l0_full) : "
                "(SELECT_AS_DATA_USED ? "
                "(MUX_SELECT_CONFIG ? _l1_pair : _l0_pair) : "
                "(S ? _l1_pair : _l0_pair));"
            ),
            "  assign O1 = _use_full ? _l1_full : _l1_pair;",
        ]

    def _select_as_data_bits(self, private_prefix: str) -> list[str]:
        """Return index bits for pair mode with select-as-data enabled."""
        normal_private_count: int = self.lut_size - self.num_shared_inputs
        if self.num_shared_inputs == 0:
            return [f"I{i}" for i in range(self.num_shared_inputs)] + [
                f"{private_prefix}{i}" for i in range(normal_private_count)
            ]

        bits: list[str] = [f"I{i}" for i in range(self.num_shared_inputs - 1)]
        bits.extend(f"{private_prefix}{i}" for i in range(normal_private_count))
        if private_prefix == "A":
            bits.append("S")
        else:
            bits.append(f"I{self.num_shared_inputs - 1}")
        return bits

    @staticmethod
    def _idx_expr(bits: list[str]) -> str:
        """Return a Verilog index concatenation expression for LUT input bits."""
        return ", ".join(reversed(bits))
