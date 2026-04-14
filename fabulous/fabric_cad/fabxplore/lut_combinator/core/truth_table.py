"""Parse, transform, and format LUT truth table INIT values.

This module centralizes conversion between textual INIT literals and integer truth
tables. It also provides pin-order remapping helpers used when source LUTs are embedded
into fractional architecture slots.
"""

import re

_LITERAL_RE = re.compile(r"^\s*(\d+)'([bBhH])([0-9a-fA-F_xXzZ]+)\s*$")


def parse_init_literal(value: str, width: int) -> int:
    """Parse an INIT literal into a masked integer truth table.

    Supported forms include Verilog-style width-qualified binary or hex
    literals, plain binary strings, ``0x``-prefixed hex, and decimal text.
    Unknown bits (``x``/``z``) are treated as zero to keep mapping deterministic.

    Parameters
    ----------
    value : str
        INIT literal text to parse.
    width : int
        LUT input width. The truth table is masked to ``2**width`` bits.

    Returns
    -------
    int
        Parsed and masked truth table value.
    """
    text: str = value.strip()
    m = _LITERAL_RE.match(text)

    if m:
        nbits: int = int(m.group(1))
        base: str = m.group(2).lower()

        digits: str = m.group(3).replace("_", "")
        digits: str = "".join("0" if ch.lower() in {"x", "z"} else ch for ch in digits)

        val: int = int(digits, 16 if base == "h" else 2)
        return _mask(val, min(nbits, 1 << width))

    if all(ch in "01xXzZ_" for ch in text):
        bits: str = "".join(
            "0" if ch.lower() in {"x", "z"} else ch for ch in text.replace("_", "")
        )
        return _mask(int(bits or "0", 2), 1 << width)

    if text.startswith("0x"):
        return _mask(int(text, 16), 1 << width)

    return _mask(int(text or "0", 10), 1 << width)


def remap_init_to_slot(
    init: int, src_width: int, input_to_slot_pin: tuple[int, ...], slot_width: int
) -> int:
    """Remap a LUT truth table from source pin order to slot pin order.

    The function enumerates all assignments of the destination slot pins, then
    reconstructs the source LUT input index according to ``input_to_slot_pin``.
    This preserves logical behavior after pin permutation during packing.

    Parameters
    ----------
    init : int
        Source LUT truth table encoded as an integer.
    src_width : int
        Number of source LUT input pins.
    input_to_slot_pin : tuple[int, ...]
        Mapping from source pin index to destination slot pin index.
    slot_width : int
        Number of pins in the destination slot truth table.

    Returns
    -------
    int
        Destination-slot truth table with remapped pin ordering.
    """
    out: int = 0
    for dst_assignment in range(1 << slot_width):
        src_index: int = 0
        for src_idx in range(src_width):
            bit: int = (dst_assignment >> input_to_slot_pin[src_idx]) & 1
            src_index |= bit << src_idx
        out |= ((init >> src_index) & 1) << dst_assignment
    return out


def format_bits(value: int, width: int) -> str:
    """Format an integer as a fixed-width binary string.

    This helper is useful for debugging INIT values and generating readable
    traces where exact bit layout must be inspected.

    Parameters
    ----------
    value : int
        Integer value to format.
    width : int
        Bit width of the output string.

    Returns
    -------
    str
        Binary string padded with leading zeros to ``width`` characters.
    """
    return f"{value:0{width}b}"


def _mask(value: int, width: int) -> int:
    """Mask an integer to the specified number of least-significant bits.

    Parameters
    ----------
    value : int
        Integer value to mask.
    width : int
        Number of low bits to keep.

    Returns
    -------
    int
        ``value`` limited to ``width`` bits.
    """
    return value & ((1 << width) - 1 if width > 0 else 0)
