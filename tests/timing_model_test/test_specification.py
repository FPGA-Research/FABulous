from pathlib import Path

import pytest

from fabulous.fabric_cad.timing_model.tools.specification import StaTool, SynthTool


class IncompleteSynthTool(SynthTool):
    pass


class CompleteSynthTool(SynthTool):
    def __init__(self) -> None:
        self._synth_design_name = "top"
        self._synth_rtl_files = [Path("a.v")]
        self._synth_liberty_files = [Path("lib.lib")]
        self._synth_passthrough = False
        self._synth_netlist_file = Path("out.v")
        self.synthesize_called = False
        self.cleanup_called = False

    def synth_synthesize(self) -> None:
        self.synthesize_called = True

    @property
    def synth_netlist_file(self) -> Path:
        return self._synth_netlist_file

    def synth_clean_up(self) -> None:
        self.cleanup_called = True

    @property
    def synth_design_name(self) -> str:
        return self._synth_design_name

    @synth_design_name.setter
    def synth_design_name(self, name: str) -> None:
        self._synth_design_name = name

    @property
    def synth_liberty_files(self) -> list[Path] | Path:
        return self._synth_liberty_files

    @synth_liberty_files.setter
    def synth_liberty_files(self, files: list[Path] | Path) -> None:
        self._synth_liberty_files = files

    @property
    def synth_rtl_files(self) -> list[Path] | Path:
        return self._synth_rtl_files

    @synth_rtl_files.setter
    def synth_rtl_files(self, files: list[Path] | Path) -> None:
        self._synth_rtl_files = files

    @property
    def synth_passthrough(self) -> bool:
        return self._synth_passthrough

    @synth_passthrough.setter
    def synth_passthrough(self, value: bool) -> None:
        self._synth_passthrough = value


class IncompleteStaTool(StaTool):
    pass


class CompleteStaTool(StaTool):
    def __init__(self) -> None:
        self._sta_design_name = "top"
        self._sta_netlist_file = Path("netlist.v")
        self._sta_liberty_files = [Path("lib.lib")]
        self._sta_rc_files = None
        self._sta_sdf_file = Path("out.sdf")
        self.analyze_called = False
        self.cleanup_called = False

    def sta_analyze(self) -> None:
        self.analyze_called = True

    @property
    def sta_sdf_file(self) -> Path:
        return self._sta_sdf_file

    def sta_clean_up(self) -> None:
        self.cleanup_called = True

    @property
    def sta_netlist_file(self) -> Path:
        return self._sta_netlist_file

    @sta_netlist_file.setter
    def sta_netlist_file(self, netl: Path) -> None:
        self._sta_netlist_file = netl

    @property
    def sta_design_name(self) -> str:
        return self._sta_design_name

    @sta_design_name.setter
    def sta_design_name(self, name: str) -> None:
        self._sta_design_name = name

    @property
    def sta_liberty_files(self) -> list[Path] | Path:
        return self._sta_liberty_files

    @sta_liberty_files.setter
    def sta_liberty_files(self, files: list[Path] | Path) -> None:
        self._sta_liberty_files = files

    @property
    def sta_rc_files(self) -> list[Path] | Path | None:
        return self._sta_rc_files

    @sta_rc_files.setter
    def sta_rc_files(self, files: list[Path] | Path | None) -> None:
        self._sta_rc_files = files


def test_incomplete_synth_tool_cannot_be_instantiated() -> None:
    with pytest.raises(TypeError):
        IncompleteSynthTool()


def test_complete_synth_tool_can_be_instantiated() -> None:
    tool = CompleteSynthTool()
    assert isinstance(tool, SynthTool)


def test_complete_synth_tool_properties_and_methods() -> None:
    tool = CompleteSynthTool()

    assert tool.synth_design_name == "top"
    assert tool.synth_rtl_files == [Path("a.v")]
    assert tool.synth_liberty_files == [Path("lib.lib")]
    assert tool.synth_netlist_file == Path("out.v")
    assert tool.synth_passthrough is False

    tool.synth_design_name = "new_top"
    tool.synth_rtl_files = Path("b.v")
    tool.synth_liberty_files = Path("new.lib")
    tool.synth_passthrough = True

    assert tool.synth_design_name == "new_top"
    assert tool.synth_rtl_files == Path("b.v")
    assert tool.synth_liberty_files == Path("new.lib")
    assert tool.synth_passthrough is True

    tool.synth_synthesize()
    tool.synth_clean_up()

    assert tool.synthesize_called is True
    assert tool.cleanup_called is True


def test_incomplete_sta_tool_cannot_be_instantiated() -> None:
    with pytest.raises(TypeError):
        IncompleteStaTool()


def test_complete_sta_tool_can_be_instantiated() -> None:
    tool = CompleteStaTool()
    assert isinstance(tool, StaTool)


def test_complete_sta_tool_properties_and_methods() -> None:
    tool = CompleteStaTool()

    assert tool.sta_design_name == "top"
    assert tool.sta_netlist_file == Path("netlist.v")
    assert tool.sta_liberty_files == [Path("lib.lib")]
    assert tool.sta_rc_files is None
    assert tool.sta_sdf_file == Path("out.sdf")

    tool.sta_design_name = "new_top"
    tool.sta_netlist_file = Path("new_netlist.v")
    tool.sta_liberty_files = Path("new.lib")
    tool.sta_rc_files = [Path("rc.spef")]

    assert tool.sta_design_name == "new_top"
    assert tool.sta_netlist_file == Path("new_netlist.v")
    assert tool.sta_liberty_files == Path("new.lib")
    assert tool.sta_rc_files == [Path("rc.spef")]

    tool.sta_analyze()
    tool.sta_clean_up()

    assert tool.analyze_called is True
    assert tool.cleanup_called is True


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
