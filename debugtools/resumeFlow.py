#!/usr/bin/env python3

# Copyright (c) 2024 Leo Moser <leomoser99@gmail.com>
# SPDX-License-Identifier: Apache-2.0

# original from https://github.com/EAS-DSD/fpga-stitching/blob/main/ol2_harden_tiles.py

import os
import sys
import time
import json
import shutil
import resource
from datetime import datetime

import common

from typing import List, Type

from openlane.common import Path
from openlane.config import Variable
from openlane.flows.misc import OpenInKLayout
from openlane.flows.misc import OpenInOpenROAD
from openlane.flows.sequential import SequentialFlow
from openlane.steps.odb import OdbpyStep
from openlane.steps import (
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


class IOPlacement(OdbpyStep):
    id = "FABulous.Tile.IOPlacement"
    name = "Custom IO placement for a fabric tile"

    config_vars = [
        Variable(
            "TILE_PATH",
            Path,
            "Points to the current tile."
        )
    ]

    def get_script_path(self):
        print(f'Loading odb_ioplace.py from {self.config["TILE_PATH"]}')
        return os.path.join(
            self.config["TILE_PATH"],
            'odb_ioplace.py'
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
        IOPlacement,
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


def harden_tile(tiles_path, tile_name, verilog_files, width, height):
    # Create and run custom flow

    design_name = tile_name

    tile_path = os.path.join(tiles_path, tile_name)

    # Get environment variables
    PDK_ROOT = os.getenv('PDK_ROOT')
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
        "FP_PDN_CFG": 'pdn/pdn_cfg.tcl',
        "FP_PDN_MULTILAYER": False,
        "FP_PDN_VOFFSET": 0,
        "FP_PDN_HOFFSET": 0,
        "FP_PDN_VWIDTH": 1.2,
        "FP_PDN_HWIDTH": 1.6,
        "FP_PDN_VSPACING": 3.8,
        "FP_PDN_HSPACING": 3.4,
        "FP_PDN_VPITCH": common.FP_PDN_VPITCH,
        "FP_PDN_HPITCH": common.FP_PDN_HPITCH,

        # Routing
        "GRT_ALLOW_CONGESTION": True,
        "RT_MAX_LAYER": "met4",
        "DRT_THREADS": 16
    }

    # Choose which flow to run
    flow_class = TileFlow
    if OPEN_IN_KLAYOUT:
        flow_class = OpenInKLayout
    if OPEN_IN_OPENROAD:
        flow_class = OpenInOpenROAD

        # Run the flow
    flow = flow_class(
        flow_cfg,
        design_dir=tile_path,
        pdk_root=PDK_ROOT,
        pdk=PDK,
        scl=SCL
    )

    flow.start(last_run=OPEN_IN_KLAYOUT or OPEN_IN_OPENROAD)

    # Save output artifacts
    os.makedirs(os.path.join(tile_path, 'macro/gds/'), exist_ok=True)
    os.makedirs(os.path.join(tile_path, 'macro/def/'), exist_ok=True)
    os.makedirs(os.path.join(tile_path, 'macro/lef/'), exist_ok=True)
    os.makedirs(os.path.join(tile_path, 'macro/nl/'), exist_ok=True)
    os.makedirs(os.path.join(tile_path, 'macro/pnl/'), exist_ok=True)
    os.makedirs(os.path.join(tile_path, 'macro/spef/'), exist_ok=True)

    file_list = sorted(os.listdir(os.path.join(tile_path, 'runs/')))

    output_dir = file_list[-1]

    shutil.copy(os.path.join(tile_path, 'runs', output_dir, f'final/gds/{design_name}.gds'),
                os.path.join(tile_path, f'macro/gds/{design_name}.gds'))
    shutil.copy(os.path.join(tile_path, 'runs', output_dir, f'final/def/{design_name}.def'),
                os.path.join(tile_path, f'macro/def/{design_name}.def'))
    shutil.copy(os.path.join(tile_path, 'runs', output_dir, f'final/lef/{design_name}.lef'),
                os.path.join(tile_path, f'macro/lef/{design_name}.lef'))
    shutil.copy(os.path.join(tile_path, 'runs', output_dir, f'final/nl/{design_name}.nl.v'),
                os.path.join(tile_path, f'macro/nl/{design_name}.nl.v'))
    shutil.copy(os.path.join(tile_path, 'runs', output_dir, f'final/pnl/{design_name}.pnl.v'),
                os.path.join(tile_path, f'macro/pnl/{design_name}.pnl.v'))

    shutil.copy(os.path.join(tile_path, 'runs', output_dir, f'final/spef/max_/{design_name}.max.spef'),
                os.path.join(tile_path, f'macro/spef/{design_name}.max.spef'))
    shutil.copy(os.path.join(tile_path, 'runs', output_dir, f'final/spef/min_/{design_name}.min.spef'),
                os.path.join(tile_path, f'macro/spef/{design_name}.min.spef'))
    shutil.copy(os.path.join(tile_path, 'runs', output_dir, f'final/spef/nom_/{design_name}.nom.spef'),
                os.path.join(tile_path, f'macro/spef/{design_name}.nom.spef'))


def main():
    date_tag = datetime.now().strftime("%Y_%m_%d_%H_%M_%S")

    # Get environment variables
    OPEN_IN_KLAYOUT = os.getenv('OPEN_IN_KLAYOUT')
    OPEN_IN_OPENROAD = os.getenv('OPEN_IN_OPENROAD')

    t_process = time.process_time()
    t_perf_counter = time.perf_counter()

    verilog_files = [
        'custom.v',
        'models_pack.v'
    ]

    verilog_files_e_io = verilog_files + [
        'Tile/E_IO/Config_access.v',
        'Tile/E_IO/IO_1_bidirectional_frame_config_pass.v',
        'Tile/E_IO/E_IO.v',
        'Tile/E_IO/E_IO_switch_matrix.v',
        'Tile/E_IO/E_IO_ConfigMem.v'
    ]

    verilog_files_w_io = verilog_files + [
        'Tile/W_IO/Config_access.v',
        'Tile/W_IO/IO_1_bidirectional_frame_config_pass.v',
        'Tile/W_IO/W_IO.v',
        'Tile/W_IO/W_IO_switch_matrix.v',
        'Tile/W_IO/W_IO_ConfigMem.v'
    ]

    verilog_files_n_io = verilog_files + [
        'Tile/N_IO/Config_access.v',
        'Tile/N_IO/IO_1_bidirectional_frame_config_pass.v',
        'Tile/N_IO/N_IO.v',
        'Tile/N_IO/N_IO_switch_matrix.v',
        'Tile/N_IO/N_IO_ConfigMem.v'
    ]

    verilog_files_s_io = verilog_files + [
        'Tile/S_IO/Config_access.v',
        'Tile/S_IO/IO_1_bidirectional_frame_config_pass.v',
        'Tile/S_IO/S_IO.v',
        'Tile/S_IO/S_IO_switch_matrix.v',
        'Tile/S_IO/S_IO_ConfigMem.v'
    ]

    verilog_files_lut4ab = verilog_files + [
        'Tile/LUT4AB/LUT4c_frame_config_dffesr.v',
        'Tile/LUT4AB/MUX8LUT_frame_config_mux.v',
        'Tile/LUT4AB/LUT4AB.v',
        'Tile/LUT4AB/LUT4AB_switch_matrix.v',
        'Tile/LUT4AB/LUT4AB_ConfigMem.v'
    ]

    verilog_files_n_term_single = verilog_files + [
        'Tile/N_term_single/N_term_single.v',
        'Tile/N_term_single/N_term_single_switch_matrix.v',
        'Tile/N_term_single/N_term_single_ConfigMem.v'
    ]

    verilog_files_s_term_single = verilog_files + [
        'Tile/S_term_single/S_term_single.v',
        'Tile/S_term_single/S_term_single_switch_matrix.v',
        'Tile/S_term_single/S_term_single_ConfigMem.v'
    ]

    # Harden each tile
    harden_tile('Tile/', 'E_IO', verilog_files_e_io, common.TILE_WIDTH / 2, common.TILE_HEIGHT)
    harden_tile('Tile/', 'W_IO', verilog_files_w_io, common.TILE_WIDTH / 2, common.TILE_HEIGHT)
    harden_tile('Tile/', 'LUT4AB', verilog_files_lut4ab, common.TILE_WIDTH, common.TILE_HEIGHT)
    harden_tile('Tile/', 'N_term_single', verilog_files_n_term_single, common.TILE_WIDTH, common.TILE_HEIGHT / 2)
    harden_tile('Tile/', 'S_term_single', verilog_files_s_term_single, common.TILE_WIDTH, common.TILE_HEIGHT / 2)
    # harden_tile('Tile/', 'N_IO', verilog_files_n_io, common.TILE_WIDTH, common.TILE_HEIGHT/2)
    # harden_tile('Tile/', 'S_IO', verilog_files_s_io, common.TILE_WIDTH, common.TILE_HEIGHT/2)

    elapsed_time_process = time.process_time() - t_process
    elapsed_time_perf_counter = time.perf_counter() - t_perf_counter

    if OPEN_IN_KLAYOUT or OPEN_IN_OPENROAD:
        return  # skip writing measurements

    # Write measurement data
    resources = {
        'max_memory': {},
        'user_time': {},
        'system_time': {},

        'elapsed_time_process': elapsed_time_process,
        'elapsed_time_perf_counter': elapsed_time_perf_counter
    }

    resources['max_memory']['RUSAGE_SELF'] = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    resources['max_memory']['RUSAGE_CHILDREN'] = resource.getrusage(resource.RUSAGE_CHILDREN).ru_maxrss
    resources['max_memory']['RUSAGE_THREAD'] = resource.getrusage(resource.RUSAGE_THREAD).ru_maxrss

    resources['user_time']['RUSAGE_SELF'] = resource.getrusage(resource.RUSAGE_SELF).ru_utime
    resources['user_time']['RUSAGE_CHILDREN'] = resource.getrusage(resource.RUSAGE_CHILDREN).ru_utime
    resources['user_time']['RUSAGE_THREAD'] = resource.getrusage(resource.RUSAGE_THREAD).ru_utime

    resources['system_time']['RUSAGE_SELF'] = resource.getrusage(resource.RUSAGE_SELF).ru_stime
    resources['system_time']['RUSAGE_CHILDREN'] = resource.getrusage(resource.RUSAGE_CHILDREN).ru_stime
    resources['system_time']['RUSAGE_THREAD'] = resource.getrusage(resource.RUSAGE_THREAD).ru_stime

    print(resources)

    os.makedirs(os.path.join('measurements/harden_tiles/'), exist_ok=True)

    with open(os.path.join('measurements/harden_tiles/', f'{date_tag}.txt'), 'w') as f:
        json.dump(resources, f)


if __name__ == "__main__":
    main()