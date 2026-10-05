from abc import ABC

import pytest

from fabulous.fabric_cad.timing_model.tools.specification import StaTool, SynthTool


@pytest.mark.parametrize(
    ("tool_cls", "expected"),
    [
        (
            SynthTool,
            {
                "synth_synthesize",
                "synth_netlist_file",
                "synth_clean_up",
                "synth_design_name",
                "synth_liberty_files",
                "synth_rtl_files",
                "synth_passthrough",
            },
        ),
        (
            StaTool,
            {
                "sta_analyze",
                "sta_sdf_file",
                "sta_clean_up",
                "sta_netlist_file",
                "sta_design_name",
                "sta_liberty_files",
                "sta_rc_files",
            },
        ),
    ],
    ids=["synth", "sta"],
)
def test_tool_interface_is_exactly_the_abstract_members(
    tool_cls: type[ABC], expected: set[str]
) -> None:
    assert tool_cls.__abstractmethods__ == frozenset(expected)
