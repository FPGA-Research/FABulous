"""Defines the standard flow for generating GDS from RTL."""

from librelane.steps import checker as Checker
from librelane.steps import klayout as KLayout
from librelane.steps import magic as Magic
from librelane.steps import misc as Misc
from librelane.steps import netgen as Netgen
from librelane.steps import odb as Odb
from librelane.steps import openroad as OpenROAD
from librelane.steps import pyosys as pyYosys
from librelane.steps import verilator as Verilator
from librelane.steps.step import Step

from fabulous.fabric_generator.gds_generator.steps.condition_magic_drc import (
    ConditionalMagicDRC,
)
from fabulous.fabric_generator.gds_generator.steps.extract_pdk_info import (
    ExtractPDKInfo,
)

prep_steps: list[type[Step]] = [
    Verilator.Lint,
    Checker.LintTimingConstructs,
    Checker.LintErrors,
    Checker.LintWarnings,
    pyYosys.JsonHeader,
    pyYosys.Synthesis,
    Checker.YosysUnmappedCells,
    Checker.YosysSynthChecks,
    Checker.NetlistAssignStatements,
    OpenROAD.CheckSDCFiles,
    OpenROAD.CheckMacroInstances,
    ExtractPDKInfo,
]

physical_steps: list[type[Step]] = [
    OpenROAD.STAPrePNR,
    OpenROAD.Floorplan,
    OpenROAD.DumpRCValues,
    Odb.CheckMacroAntennaProperties,
    Odb.SetPowerConnections,
    Odb.ManualMacroPlacement,
    OpenROAD.CutRows,
    OpenROAD.TapEndcapInsertion,
    Odb.AddPDNObstructions,
    OpenROAD.GeneratePDN,
    Odb.RemovePDNObstructions,
    Odb.AddRoutingObstructions,
    OpenROAD.GlobalPlacementSkipIO,
    Odb.CustomIOPlacement,
    Odb.ApplyDEFTemplate,
    OpenROAD.GlobalPlacement,
    Odb.WriteVerilogHeader,
    Checker.PowerGridViolations,
    OpenROAD.STAMidPNR,
    OpenROAD.RepairDesignPostGPL,
    Odb.ManualGlobalPlacement,
    OpenROAD.DetailedPlacement,
    OpenROAD.CTS,
    OpenROAD.STAMidPNR,
    OpenROAD.ResizerTimingPostCTS,
    OpenROAD.STAMidPNR,
    OpenROAD.GlobalRouting,
    OpenROAD.CheckAntennas,
    OpenROAD.RepairDesignPostGRT,
    Odb.DiodesOnPorts,
    Odb.HeuristicDiodeInsertion,
    OpenROAD.RepairAntennas,
    OpenROAD.ResizerTimingPostGRT,
    OpenROAD.STAMidPNR,
    OpenROAD.DetailedRouting,
    Odb.RemoveRoutingObstructions,
    OpenROAD.CheckAntennas,
    Checker.TrDRC,
    Odb.ReportDisconnectedPins,
    Checker.DisconnectedPins,
    Odb.ReportWireLength,
    Checker.WireLength,
    OpenROAD.FillInsertion,
    Odb.CellFrequencyTables,
    OpenROAD.RCX,
    OpenROAD.STAPostPNR,
    OpenROAD.IRDropReport,
]

write_out_steps: list[type[Step]] = [
    Magic.StreamOut,
    KLayout.StreamOut,
    Magic.WriteLEF,
]

check_steps: list[type[Step]] = [
    Odb.CheckDesignAntennaProperties,
    KLayout.XOR,
    Checker.XOR,
    KLayout.DRC,
    ConditionalMagicDRC,
    Checker.KLayoutDRC,
    Checker.MagicDRC,
    Magic.SpiceExtraction,
    Checker.IllegalOverlap,
    Netgen.LVS,
    Checker.LVS,
    Checker.SetupViolations,
    Checker.HoldViolations,
    Checker.MaxSlewViolations,
    Checker.MaxCapViolations,
    Misc.ReportManufacturability,
]


classic_gating_config_vars: dict[str, list[str]] = {
    "OpenROAD.RepairDesignPostGPL": ["RUN_POST_GPL_DESIGN_REPAIR"],
    "OpenROAD.RepairDesignPostGRT": ["RUN_POST_GRT_DESIGN_REPAIR"],
    "OpenROAD.ResizerTimingPostCTS": ["RUN_POST_CTS_RESIZER_TIMING"],
    "OpenROAD.ResizerTimingPostGRT": ["RUN_POST_GRT_RESIZER_TIMING"],
    "OpenROAD.CTS": ["RUN_CTS"],
    "OpenROAD.RCX": ["RUN_SPEF_EXTRACTION"],
    "OpenROAD.TapEndcapInsertion": ["RUN_TAP_ENDCAP_INSERTION"],
    "Odb.HeuristicDiodeInsertion": ["RUN_HEURISTIC_DIODE_INSERTION"],
    "OpenROAD.RepairAntennas": ["RUN_ANTENNA_REPAIR"],
    "OpenROAD.DetailedRouting": ["RUN_DRT"],
    "OpenROAD.FillInsertion": ["RUN_FILL_INSERTION"],
    "OpenROAD.STAPostPNR": ["RUN_MCSTA"],
    "OpenROAD.IRDropReport": ["RUN_IRDROP_REPORT"],
    "Magic.StreamOut": ["RUN_MAGIC_STREAMOUT"],
    "KLayout.StreamOut": ["RUN_KLAYOUT_STREAMOUT"],
    "Magic.WriteLEF": ["RUN_MAGIC_WRITE_LEF"],
    "Magic.DRC": ["RUN_MAGIC_DRC"],
    "KLayout.DRC": ["RUN_KLAYOUT_DRC"],
    "KLayout.XOR": [
        "RUN_KLAYOUT_XOR",
        "RUN_MAGIC_STREAMOUT",
        "RUN_KLAYOUT_STREAMOUT",
    ],
    "Netgen.LVS": ["RUN_LVS"],
    "Checker.TrDRC": ["RUN_DRT"],
    "Checker.MagicDRC": ["RUN_MAGIC_DRC"],
    "Checker.XOR": [
        "RUN_KLAYOUT_XOR",
        "RUN_MAGIC_STREAMOUT",
        "RUN_KLAYOUT_STREAMOUT",
    ],
    "Checker.LVS": ["RUN_LVS"],
    "Checker.KLayoutDRC": ["RUN_KLAYOUT_DRC"],
    # Not in VHDLClassic
    "Yosys.EQY": ["RUN_EQY"],
    "Verilator.Lint": ["RUN_LINTER"],
    "Checker.LintErrors": ["RUN_LINTER"],
    "Checker.LintWarnings": ["RUN_LINTER"],
    "Checker.LintTimingConstructs": [
        "RUN_LINTER",
    ],
}
