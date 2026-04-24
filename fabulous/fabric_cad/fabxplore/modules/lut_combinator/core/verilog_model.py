"""Verilog behavioral models for LUT combinator architecture cells."""

from dataclasses import dataclass

from jinja2 import Environment

_VERILOG_ENV = Environment(
    autoescape=False,
    keep_trailing_newline=True,
    lstrip_blocks=True,
    trim_blocks=True,
)

_FRAC_LUT_BEHAVIORAL_MODEL_TEMPLATE: str = """\
module {{ name }}({{ all_ports | join(', ') }});
{% if shared_ports %}
  input {{ shared_ports | join(', ') }};
{% endif %}
{% if a_ports %}
  input {{ a_ports | join(', ') }};
{% endif %}
{% if b_ports %}
  input {{ b_ports | join(', ') }};
{% endif %}
  input S;
  output O0, O1;

  parameter META_DATA = "";
  parameter L0_CELL_ID = "";
  parameter L1_CELL_ID = "";
{% if include_equiv_compat_params %}
  parameter F0_CELL_ID = "";
  parameter F1_CELL_ID = "";
{% endif %}
  parameter SELECT_AS_DATA_CAPABLE = 0;
  parameter SELECT_AS_DATA_USED = 0;
  parameter EFFECTIVE_SHARED_INPUTS = {{ num_shared_inputs }};
  parameter CUT_SHARED_INDEX = -1;
  parameter MUX_SELECT_CONFIG = 0;
{% if include_equiv_compat_params %}
  parameter [255:0] MAPPED_FROM = 256'b0;
{% endif %}
  parameter [{{ init_msb }}:0] L0_INIT = {{ init_width }}'b0;
  parameter [{{ init_msb }}:0] L1_INIT = {{ init_width }}'b0;
{% if include_equiv_compat_params %}
  parameter [{{ init_msb }}:0] F0_INIT = {{ init_width }}'b0;
  parameter [{{ init_msb }}:0] F1_INIT = {{ init_width }}'b0;
{% endif %}
  parameter LUT_SIZE = "{{ lut_size }}";
  parameter NUM_SHARED_INPUTS = "{{ num_shared_inputs }}";

  wire [{{ lut_msb }}:0] _idx0_normal = { {{- idx0_normal -}} };
  wire [{{ lut_msb }}:0] _idx1_normal = { {{- idx1_normal -}} };
  wire [{{ lut_msb }}:0] _idx0_cut = { {{- idx0_cut -}} };
  wire [{{ lut_msb }}:0] _idx1_cut = { {{- idx1_cut -}} };
  wire [{{ lut_msb }}:0] _idx0_pair = SELECT_AS_DATA_USED ? _idx0_cut : _idx0_normal;
  wire [{{ lut_msb }}:0] _idx1_pair = SELECT_AS_DATA_USED ? _idx1_cut : _idx1_normal;

{% if include_equiv_compat_params %}
  wire [{{ lut_msb }}:0] _idx_full = { {{- idx_full -}} };
  wire [{{ init_msb }}:0] _i0 = L0_INIT | F0_INIT;
  wire [{{ init_msb }}:0] _i1 = L1_INIT | F1_INIT;
  wire _l0_pair = _i0[_idx0_pair];
  wire _l1_pair = _i1[_idx1_pair];
  wire _l0_full = _i0[_idx_full];
  wire _l1_full = _i1[_idx_full];
  wire _use_full = |MAPPED_FROM;

  assign O0 = _use_full ? (S ? _l1_full : _l0_full) :
              (SELECT_AS_DATA_USED ?
               (MUX_SELECT_CONFIG ? _l1_pair : _l0_pair) :
               (S ? _l1_pair : _l0_pair));
  assign O1 = _use_full ? _l1_full : _l1_pair;
{% else %}
  wire _l0_pair = L0_INIT[_idx0_pair];
  wire _l1_pair = L1_INIT[_idx1_pair];

  assign O0 = SELECT_AS_DATA_USED ?
              (MUX_SELECT_CONFIG ? _l1_pair : _l0_pair) :
              (S ? _l1_pair : _l0_pair);
  assign O1 = _l1_pair;
{% endif %}
endmodule
"""

_FRAC_LUT_BEHAVIORAL_MODEL = _VERILOG_ENV.from_string(
    _FRAC_LUT_BEHAVIORAL_MODEL_TEMPLATE
)


@dataclass(frozen=True)
class FracLutBehavioralModel:
    """Generate the behavioral Verilog model for a fractional LUT cell.

    The model is shared by the Pyosys pass and equivalence checker so both places
    elaborate the same FRAC LUT semantics.

    Attributes
    ----------
    name : str
        Verilog module name to generate for the fractional LUT cell.
    lut_size : int
        Number of inputs ``K`` on each internal LUT half.
    num_shared_inputs : int
        Number of nominal shared input pins ``I*`` exposed by the architecture.
    interface_width : int | None
        Optional widened interface size for generated ``I*``, ``A*``, and ``B*``
        ports. When ``None``, the model emits only the architecture's nominal
        port set. The equivalence checker uses a wider value so named-port
        instances with extra unused pins still elaborate.
    include_equiv_compat_params : bool
        Whether to include compatibility parameters and full-LUT fallback logic
        used by the standalone equivalence checker.
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
        """Return the behavioral model as Verilog source text.

        Returns
        -------
        str
            Complete Verilog module text for the configured FRAC LUT model.
        """
        return _FRAC_LUT_BEHAVIORAL_MODEL.render(self._template_context())

    def to_lines(self) -> list[str]:
        """Return the behavioral model as Verilog source lines.

        Returns
        -------
        list[str]
            Verilog module text split into individual lines.
        """
        return self.to_verilog().splitlines()

    def _template_context(self) -> dict[str, object]:
        """Return the Jinja context for rendering the behavioral model.

        Returns
        -------
        dict[str, object]
            Values consumed by the FRAC LUT behavioral-model template.
        """
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

        l0_bits: list[str] = [f"I{i}" for i in range(s)] + [f"A{i}" for i in range(p)]
        l1_bits: list[str] = [f"I{i}" for i in range(s)] + [f"B{i}" for i in range(p)]
        full_bits: list[str] = [f"I{i}" for i in range(k)]

        return {
            "name": self.name,
            "lut_size": k,
            "lut_msb": k - 1,
            "num_shared_inputs": s,
            "init_width": init_width,
            "init_msb": init_width - 1,
            "shared_ports": shared_ports,
            "a_ports": a_ports,
            "b_ports": b_ports,
            "all_ports": shared_ports + a_ports + b_ports + ["S", "O0", "O1"],
            "idx0_normal": self._idx_expr(l0_bits),
            "idx1_normal": self._idx_expr(l1_bits),
            "idx0_cut": self._idx_expr(self._select_as_data_bits("A")),
            "idx1_cut": self._idx_expr(self._select_as_data_bits("B")),
            "idx_full": self._idx_expr(full_bits),
            "include_equiv_compat_params": self.include_equiv_compat_params,
        }

    def _select_as_data_bits(self, private_prefix: str) -> list[str]:
        """Return index bits for pair mode with select-as-data enabled.

        Parameters
        ----------
        private_prefix : str
            Private input prefix for the internal LUT side, either ``"A"`` for
            L0 or ``"B"`` for L1.

        Returns
        -------
        list[str]
            Ordered LUT index bits before conversion to Verilog concatenation
            syntax.
        """
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
        """Return a Verilog index concatenation expression for LUT input bits.

        Parameters
        ----------
        bits : list[str]
            Ordered LUT index bits from least significant to most significant.

        Returns
        -------
        str
            Comma-separated Verilog expression ordered for concatenation.
        """
        return ", ".join(reversed(bits))
