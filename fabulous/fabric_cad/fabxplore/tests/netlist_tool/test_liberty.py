"""Tests for netlist-tool Liberty text edits."""

import pytest

from fabulous.fabric_cad.fabxplore.modules.netlist_tool.core.liberty import (
    LibertyHandler,
)
from fabulous.fabric_cad.fabxplore.modules.netlist_tool.core.models import (
    PdkInputConfig,
)

BASE_LIBERTY = """
library ("test") {
  cell ("BASE") {
    area : 1.0;
  }
}
"""


def test_add_liberty_cells_rejects_non_cell_text() -> None:
    """Keep cell-only insertion strict for backwards compatibility."""
    fragment = """
lu_table_template(custom_delay) {
  variable_1 : input_net_transition;
}

cell ("CUSTOM") {
  area : 2.0;
}
"""
    handler = LibertyHandler(
        _config(
            add_liberty_cells=[fragment],
        )
    )

    with pytest.raises(
        ValueError,
        match="Liberty cell fragment contains text outside cell blocks",
    ):
        handler.modify_liberty(BASE_LIBERTY)


def test_inject_liberty_fragments_accepts_templates_and_cells() -> None:
    """Inject library-level Liberty text before the library close."""
    fragment = """
lu_table_template(custom_delay) {
  variable_1 : input_net_transition;
}

cell ("CUSTOM") {
  area : 2.0;
}
"""
    result = LibertyHandler(
        _config(
            inject_liberty_fragments=[fragment],
        )
    ).modify_liberty(BASE_LIBERTY)

    assert "lu_table_template(custom_delay)" in result
    assert 'cell ("CUSTOM")' in result
    assert result.index('cell ("BASE")') < result.index(
        "lu_table_template(custom_delay)"
    )
    assert result.rfind('cell ("CUSTOM")') < result.rfind("}")


def test_inject_liberty_fragments_rejects_empty_fragments() -> None:
    """Reject fragment entries that would silently do nothing."""
    handler = LibertyHandler(
        _config(
            inject_liberty_fragments=["/* only a comment */\n"],
        )
    )

    with pytest.raises(ValueError, match="Injected Liberty fragment is empty"):
        handler.modify_liberty(BASE_LIBERTY)


def _config(**kwargs: object) -> PdkInputConfig:
    """Create a minimal netlist-tool config for LibertyHandler tests."""
    return PdkInputConfig(top_name="top", rtl_files=[], **kwargs)
