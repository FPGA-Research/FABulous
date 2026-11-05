# Copyright 2025 LibreLane Contributors
#
# Adapted from OpenLane
#
# Copyright 2020-2022 Efabless Corporation
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#      http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
#
# Copyright (c) 2026 FABulous Contributors
#
# LibreLane 3.1.0.dev3 `scripts/openroad/pdn.tcl` with the grid definitions of
# `scripts/openroad/common/pdn_cfg.tcl` inlined and reduced to what a tile uses:
# vertical stripes on one layer, extended to the boundary and promoted to pins, the
# standard cell rails and the macro grid. The fabric draws the horizontal layer
# across the tiles. `FABulousTilePDN` rejects the other LibreLane PDN modes and
# plans the stripe placement, which this script only replays.

source $::env(SCRIPTS_DIR)/openroad/common/io.tcl
read_current_odb

source $::env(SCRIPTS_DIR)/openroad/common/set_power_nets.tcl
source $::env(SCRIPTS_DIR)/openroad/common/set_global_connections.tcl
set_global_connections

set secondary []
foreach vdd $::env(VDD_NETS) gnd $::env(GND_NETS) {
    if { $vdd != $::env(VDD_NET)} {
        lappend secondary $vdd

        set db_net [[ord::get_db_block] findNet $vdd]
        if {$db_net == "NULL"} {
            set net [odb::dbNet_create [ord::get_db_block] $vdd]
            $net setSpecial
            $net setSigType "POWER"
        }
    }

    if { $gnd != $::env(GND_NET)} {
        lappend secondary $gnd

        set db_net [[ord::get_db_block] findNet $gnd]
        if {$db_net == "NULL"} {
            set net [odb::dbNet_create [ord::get_db_block] $gnd]
            $net setSpecial
            $net setSigType "GROUND"
        }
    }
}

set_voltage_domain -name CORE -power $::env(VDD_NET) -ground $::env(GND_NET) \
    -secondary_power $secondary

define_pdn_grid \
    -name stdcell_grid \
    -starts_with POWER \
    -voltage_domain CORE \
    -pins $::env(PDN_VERTICAL_LAYER)

# `FABulousTilePDN` writes one `net offset count` stripe train per line.
set stripes_file [open $::env(STEP_DIR)/pdn_stripes.txt]
set stripes [read $stripes_file]
close $stripes_file
foreach {net offset count} $stripes {
    add_pdn_stripe \
        -grid stdcell_grid \
        -layer $::env(PDN_VERTICAL_LAYER) \
        -width $::env(PDN_VWIDTH) \
        -pitch $::env(PDN_VPITCH) \
        -offset $offset \
        -nets $net \
        -number_of_straps $count \
        -extend_to_boundary
}

if { $::env(PDN_ENABLE_RAILS) == 1 } {
    add_pdn_stripe \
        -grid stdcell_grid \
        -layer $::env(PDN_RAIL_LAYER) \
        -width $::env(PDN_RAIL_WIDTH) \
        -followpins

    add_pdn_connect \
        -grid stdcell_grid \
        -layers "$::env(PDN_RAIL_LAYER) $::env(PDN_VERTICAL_LAYER)"
}

define_pdn_grid \
    -macro \
    -default \
    -name macro \
    -starts_with POWER \
    -halo "$::env(PDN_HORIZONTAL_HALO) $::env(PDN_VERTICAL_HALO)"

add_pdn_connect \
    -grid macro \
    -layers "$::env(PDN_VERTICAL_LAYER) $::env(PDN_HORIZONTAL_LAYER)"

set arg_list [list]
if { $::env(PDN_SKIPTRIM) } {
    lappend arg_list -skip_trim
}
if {[catch {log_cmd pdngen {*}$arg_list} errmsg]} {
    puts stderr $errmsg
    exit_unless_gui 1
} else {
    write_views
    report_design_area_metrics

    foreach {net} "$::env(VDD_NETS) $::env(GND_NETS)" {
        set report_file $::env(STEP_DIR)/$net-grid-errors.rpt

        # check_power_grid passes when it finds no nodes at all, so an empty report
        # stands in for a grid that failed to generate.
        set f [open $report_file "w"]
        puts $f ""
        close $f

        if { [catch {check_power_grid -net $net -error_file $report_file} err] } {
            puts stderr "\[WARNING\] Grid check for $net failed: $err"
        }
    }
}
