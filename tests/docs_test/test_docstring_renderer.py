"""Tests for the AutoAPI jinja filters in `docs/source/_ext/docstring_renderer.py`.

Docstring *markup* is no longer translated: the `myst_docstring` directive parses
docstrings with the MyST parser directly. What is left here shapes the reST page
body AutoAPI generates around the docstring, so a regression shows up as a
malformed API page rather than a failed build.
"""

import importlib.util
import sys
from pathlib import Path
from types import ModuleType

import pytest

_RENDERER_PATH = (
    Path(__file__).parents[2] / "docs" / "source" / "_ext" / "docstring_renderer.py"
)


def _load_renderer() -> ModuleType:
    """Import the docstring renderer from the docs extension directory.

    Returns
    -------
    ModuleType
        The imported `docstring_renderer` module.
    """
    spec = importlib.util.spec_from_file_location("docstring_renderer", _RENDERER_PATH)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


renderer = _load_renderer()


@pytest.mark.parametrize(
    ("docstring", "expected"),
    [
        # Napoleon has already rewritten the numpy sections by the time this runs,
        # so a return section arrives as a field...
        pytest.param(
            "The tile name.\n\n:returns: The name.\n:rtype: str\n",
            "The tile name.",
            id="return-fields",
        ),
        # ...but a section napoleon does not recognise survives as a section.
        pytest.param(
            "The tile name.\n\nReturns\n-------\nstr\n    The name.\n",
            "The tile name.",
            id="return-section",
        ),
        pytest.param(
            "The tile name.\n\nReturn type\n-----------\nstr\n",
            "The tile name.",
            id="return-type-section",
        ),
        # Prose after the section is kept: the blank line closes the section.
        pytest.param(
            "The tile name.\n\nReturns\n-------\nstr\n    The name.\n\nSet at parse.",
            "The tile name.\n\nSet at parse.",
            id="following-prose-is-kept",
        ),
    ],
)
def test_property_return_sections_are_stripped(docstring: str, expected: str) -> None:
    """A property's return section duplicates its rendered type, so drop it.

    Parameters
    ----------
    docstring : str
        The property docstring.
    expected : str
        The docstring with its redundant return sections removed.
    """
    assert renderer.strip_property_return_sections(docstring) == expected


@pytest.mark.parametrize(
    ("bases", "expected"),
    [
        pytest.param(
            ["pkg.mod.Base"],
            "**Bases:** :py:class:`Base <pkg.mod.Base>`",
            id="qualified-base",
        ),
        pytest.param(["object"], "", id="object-is-noise"),
    ],
)
def test_inheritance_renders_as_rest(bases: list[str], expected: str) -> None:
    """Base classes land in the reST page body, so they stay reST.

    Parameters
    ----------
    bases : list[str]
        The class's base names.
    expected : str
        The reST the AutoAPI template should receive.
    """
    assert renderer.format_inheritance_for_rst(bases, "Child") == expected
