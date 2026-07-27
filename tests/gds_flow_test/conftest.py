"""Fixtures shared across the GDS flow tests."""

from pathlib import Path

import pytest

# The BRAM tile from the issue that motivated macro placement modes.
MACRO_MODULE = "sram"
MACRO_WIDTH = "703.02"
MACRO_HEIGHT = "737.94"


@pytest.fixture
def macro_lef(tmp_path: Path) -> Path:
    """Write a minimal LEF declaring the SRAM macro footprint."""
    lef = tmp_path / f"{MACRO_MODULE}.lef"
    lef.write_text(
        "VERSION 5.7 ;\n"
        'BUSBITCHARS "[]" ;\n'
        'DIVIDERCHAR "/" ;\n'
        "UNITS\n"
        "  DATABASE MICRONS 1000 ;\n"
        "END UNITS\n"
        f"MACRO {MACRO_MODULE}\n"
        "  CLASS BLOCK ;\n"
        "  ORIGIN 0 0 ;\n"
        f"  SIZE {MACRO_WIDTH} BY {MACRO_HEIGHT} ;\n"
        f"END {MACRO_MODULE}\n"
        "END LIBRARY\n"
    )
    return lef
