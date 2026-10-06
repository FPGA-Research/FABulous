from fabulous.fabric_cad.timing_model.tools.specification import StaTool, SynthTool


def test_synthtool_is_abstract() -> None:
    assert "synth_synthesize" in SynthTool.__abstractmethods__
    assert "synth_netlist_file" in SynthTool.__abstractmethods__
    assert "synth_clean_up" in SynthTool.__abstractmethods__
    assert "synth_design_name" in SynthTool.__abstractmethods__
    assert "synth_liberty_files" in SynthTool.__abstractmethods__
    assert "synth_rtl_files" in SynthTool.__abstractmethods__
    assert "synth_passthrough" in SynthTool.__abstractmethods__


def test_statool_is_abstract() -> None:
    assert "sta_analyze" in StaTool.__abstractmethods__
    assert "sta_sdf_file" in StaTool.__abstractmethods__
    assert "sta_clean_up" in StaTool.__abstractmethods__
    assert "sta_netlist_file" in StaTool.__abstractmethods__
    assert "sta_design_name" in StaTool.__abstractmethods__
    assert "sta_liberty_files" in StaTool.__abstractmethods__
    assert "sta_rc_files" in StaTool.__abstractmethods__
