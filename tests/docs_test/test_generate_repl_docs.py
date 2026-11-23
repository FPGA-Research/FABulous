"""Tests for the REPL reference generator in `docs/source/_ext/generate_repl_docs.py`.

The generator writes a page that is not committed, so a regression shows up as a
wrongly grouped or mis-headed reference page rather than a failed build.
"""

import importlib.util
import sys
from pathlib import Path
from types import ModuleType

import pytest
from cmd2 import CommandSet, constants
from pytest_mock import MockerFixture

from fabulous.fabulous_repl.command_set_base import CMD_SETUP

_EXT_DIR = Path(__file__).parents[2] / "docs" / "source" / "_ext"


def _load_generator() -> ModuleType:
    """Import the REPL docs generator from the docs extension directory.

    Returns
    -------
    ModuleType
        The imported `generate_repl_docs` module.
    """
    # The generator imports its sibling `_doc_common` as a top-level module.
    sys.path.insert(0, str(_EXT_DIR))
    path = _EXT_DIR / "generate_repl_docs.py"
    spec = importlib.util.spec_from_file_location("generate_repl_docs", path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


generator = _load_generator()


@pytest.mark.parametrize(
    ("docstring", "expected"),
    [
        pytest.param(
            "Summary.\n\nNotes\n-----\nA caveat.",
            "Summary.\n\n**Notes**\nA caveat.",
            id="notes-becomes-bold-label",
        ),
        pytest.param(
            "Summary.\n\nSee Also\n--------\nother_cmd",
            "Summary.\n\n**See Also**\nother_cmd",
            id="see-also-becomes-bold-label",
        ),
        pytest.param(
            "Summary.\n\nParameters\n----------\nx : int\n    A value.\n\nTail.",
            "Summary.\n\nTail.",
            id="parameters-dropped",
        ),
        pytest.param(
            "Summary.\n\nRaises\n------\nValueError\n\nNotes\n-----\nKept.",
            "Summary.\n\n**Notes**\nKept.",
            id="raises-dropped-notes-kept",
        ),
    ],
)
def test_clean_docstring(docstring: str, expected: str) -> None:
    """Call-signature sections are dropped and kept sections lose their underline."""
    assert generator.clean_docstring(docstring) == expected


def test_commands_take_their_command_set_category() -> None:
    """An undecorated command is grouped under its `CommandSet`'s category."""
    commands_by_category = generator.collect_commands()
    for cls in generator.command_classes():
        for name, member in vars(cls).items():
            if not name.startswith("do_") or hasattr(
                member, constants.COMMAND_ATTR_HELP_CATEGORY
            ):
                continue
            entries = commands_by_category[cls.DEFAULT_CATEGORY]
            assert name[3:] in [entry["name"] for entry in entries]
    assert commands_by_category[CMD_SETUP]


def test_unknown_category_fails(mocker: MockerFixture) -> None:
    """A command whose category is not a `CMD_*` constant stops the build."""

    class UncategorisedCommandSet(CommandSet):
        def do_orphan(self) -> None:
            """Have no category."""

    mocker.patch.object(
        generator, "command_classes", return_value=[UncategorisedCommandSet]
    )
    with pytest.raises(ValueError, match="do_orphan"):
        generator.collect_commands()
