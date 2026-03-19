#!/usr/bin/env python3

# Copyright (c) 2024 Leo Moser <leomoser99@gmail.com>
# SPDX-License-Identifier: Apache-2.0

import os
import sys
import time
import json
import shutil
import resource
from datetime import datetime

#import common

from typing import List, Type

from librelane.common import Path
from librelane.config import Variable
from librelane.flows.misc import OpenInKLayout
from librelane.flows.misc import OpenInOpenROAD
from librelane.flows.sequential import SequentialFlow
from librelane.steps.odb import OdbpyStep
from librelane.steps import (
    Step,
    Yosys,
    OpenROAD,
    Magic,
    Misc,
    KLayout,
    Odb,
    Netgen,
    Checker,
)




class TileFlow(SequentialFlow):
    Steps: List[Type[Step]] = [
        Yosys.JsonHeader,
        Yosys.Synthesis,
        Checker.YosysUnmappedCells,
        Checker.YosysSynthChecks,
        OpenROAD.CheckSDCFiles,
        OpenROAD.Floorplan,
        Odb.SetPowerConnections,
        Odb.ManualMacroPlacement,
        OpenROAD.CutRows,
        OpenROAD.TapEndcapInsertion,
        #IOPlacement,
        OpenROAD.GlobalPlacement,
        Odb.AddPDNObstructions,
        OpenROAD.GeneratePDN,
        Odb.RemovePDNObstructions,
        Checker.PowerGridViolations,
        OpenROAD.RepairDesignPostGPL,
        OpenROAD.DetailedPlacement,
        OpenROAD.CTS,
        OpenROAD.ResizerTimingPostCTS,
        OpenROAD.GlobalRouting,
        OpenROAD.CheckAntennas,
        OpenROAD.RepairDesignPostGRT,
        Odb.DiodesOnPorts,
        Odb.HeuristicDiodeInsertion,
        OpenROAD.RepairAntennas,
        OpenROAD.ResizerTimingPostGRT,
        OpenROAD.DetailedRouting,
        OpenROAD.CheckAntennas,
        Checker.TrDRC,
        Odb.ReportDisconnectedPins,
        Checker.DisconnectedPins,
        Odb.ReportWireLength,
        Checker.WireLength,
        OpenROAD.FillInsertion,
        OpenROAD.RCX,
        OpenROAD.STAPostPNR,
        OpenROAD.IRDropReport,
        Magic.StreamOut,
        KLayout.StreamOut,
        Magic.WriteLEF,
        KLayout.XOR,
        Checker.XOR,
        Magic.DRC,
        KLayout.DRC,
        Checker.MagicDRC,
        Checker.KLayoutDRC,
        Magic.SpiceExtraction,
        Checker.IllegalOverlap,
        Netgen.LVS,
        Checker.LVS,
        # Yosys.EQY,
        Checker.SetupViolations,
        Checker.HoldViolations,
        Misc.ReportManufacturability
    ]


def harden_tile(tiles_path, tile_name, verilog_files, width, height, openOpenroad=True, openKlayout=False):
    # Create and run custom flow

    design_name = tile_name

    tile_path = os.path.join(tiles_path, tile_name)

    # Get environment variables
    PDK_ROOT = os.getenv('FAB_PDK_ROOT')
    PDK = os.getenv('PDK_ROOT', 'sky130A')
    SCL = os.getenv('SCL')
    OPEN_IN_KLAYOUT = os.getenv('OPEN_IN_KLAYOUT')
    OPEN_IN_OPENROAD = os.getenv('OPEN_IN_OPENROAD')
    NO_CHECKS = os.getenv('NO_CHECKS')

    omit_steps = [
        'OpenROAD.STAPrePNR',
        'OpenROAD.STAMidPNR',
        'OpenROAD.STAMidPNR-1',
        'OpenROAD.STAMidPNR-2',
        'OpenROAD.STAMidPNR-3',
        'OpenROAD.STAPostPNR',
        'KLayout.XOR',
        'Checker.XOR',
        'Magic.DRC',
        'KLayout.DRC',
        'Checker.MagicDRC',
        'Checker.KLayoutDRC',
        'Magic.SpiceExtraction',
        'Checker.IllegalOverlap',
        'Netgen.LVS',
        'Checker.LVS'
    ]

    if NO_CHECKS:
        for step in list(TileFlow.Steps):
            for omit_step in omit_steps:
                if step.id.startswith(omit_step):
                    TileFlow.Steps.remove(step)
                    break

    flow_cfg = {
        # Name
        "DESIGN_NAME": design_name,

        # Sources
        "VERILOG_FILES": verilog_files,
        "TILE_PATH": tile_path,

        # CTS
        "CLOCK_PORT": "UserCLK",
        "CLOCK_PERIOD": 100,

        # Floorplanning
        "DIE_AREA": [0, 0, width, height],
        "FP_SIZING": "absolute",
        "PL_TARGET_DENSITY_PCT": 50.0,

        # Power Distribution Network
        #"FP_PDN_CFG": 'pdn/pdn_cfg.tcl',
        "FP_PDN_MULTILAYER": False,
        "FP_PDN_VOFFSET": 0,
        "FP_PDN_HOFFSET": 0,
        "FP_PDN_VWIDTH": 1.2,
        "FP_PDN_HWIDTH": 1.6,
        "FP_PDN_VSPACING": 3.8,
        "FP_PDN_HSPACING": 3.4,
        "FP_PDN_VPITCH": 40,
        "FP_PDN_HPITCH": 40,

        # Routing
        "GRT_ALLOW_CONGESTION": True,
        "RT_MAX_LAYER": "M4",
        "DRT_THREADS": 16
    }

    flow_class = OpenInOpenROAD

        # Run the flow
    flow = flow_class(
        flow_cfg,
        design_dir=tile_path,
        pdk_root=PDK_ROOT,
        pdk=PDK,
        #scl=SCL
    )

    flow.start(last_run=true)


def main():


    verilog_files = [
        'Fabric/models_pack.v'
    ]

    verilog_files_lut4ab = verilog_files + [
        'Tile/LUT4AB/LUT4c_frame_config_dffesr.v',
        'Tile/LUT4AB/MUX8LUT_frame_config_mux.v',
        'Tile/LUT4AB/LUT4AB.v',
        'Tile/LUT4AB/LUT4AB_switch_matrix.v',
        'Tile/LUT4AB/LUT4AB_ConfigMem.v'
    ]

    # Harden each tile
    harden_tile('Tile/', 'LUT4AB', verilog_files_lut4ab, 240, 240)

if __name__ == "__main__":
    main()