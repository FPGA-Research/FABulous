"""Tests for `VHDLCodeGenerator.addComponentDeclarationForFile`."""

from collections.abc import Callable
from pathlib import Path

import pytest

from fabulous.fabric_generator.code_generator.code_generator import CodeGenerator


@pytest.mark.parametrize(
    ("source", "expected_error"),
    [
        pytest.param("entity T is\nend entity T;\n", None, id="entity"),
        pytest.param(
            "package T is\nend package T;\n", "has no `entity", id="no_entity"
        ),
    ],
)
def test_component_declaration_for_file(
    tmp_path: Path,
    code_generator_factory: Callable[[str, str], CodeGenerator],
    source: str,
    expected_error: str | None,
) -> None:
    """An entity becomes a component; a file without one fails naming the file."""
    vhdl = tmp_path / "T.vhdl"
    vhdl.write_text(source)
    writer = code_generator_factory(".vhd", "top")

    if expected_error is None:
        writer.addComponentDeclarationForFile(str(vhdl))
        writer.writeToFile()
        assert "component T is\nend component T;" in writer.outFileName.read_text()
    else:
        with pytest.raises(ValueError, match=f"{vhdl} {expected_error}"):
            writer.addComponentDeclarationForFile(str(vhdl))
