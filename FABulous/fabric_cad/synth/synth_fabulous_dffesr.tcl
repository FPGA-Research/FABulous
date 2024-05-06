# Usage
# tcl synth_generic.tcl {K} {out.json}

set LUT_K 4
if {$argc > 0} { set LUT_K [lindex $argv 0] }
set for_vpr [expr {[file extension [lindex $argv 2]] == ".blif"}]
yosys read_verilog -lib [file dirname [file normalize $argv0]]/prims_ff.v
yosys hierarchy -check -top [lindex $argv 1]
yosys proc
#yosys flatten
yosys tribuf -logic
yosys deminout
yosys synth -run coarse
yosys memory_map
yosys opt -full
yosys techmap -map +/techmap.v
yosys opt -fast
#yosys dfflegalize -cell \$_DFF_P_ 0 -cell \$_DFFE_PP_ 0 -cell \$_SDFF_PP1_ 0 -cell \$_SDFF_PP0_ 0 -cell \$_SDFFCE_PP1P_ 0 -cell \$_SDFFCE_PP0P_ 0 -cell \$_DLATCH_?_ x
yosys dfflegalize -cell \$_DFF_P_ 0 -cell \$_DFFE_PP_ 0 -cell \$_SDFF_PP?_ 0 -cell \$_SDFFCE_PP?P_ 0 -cell \$_DLATCH_?_ x
yosys techmap -map [file dirname [file normalize $argv0]]/ff_map.v
yosys opt_expr -mux_undef
yosys simplemap
yosys techmap -map [file dirname [file normalize $argv0]]/latches_map.v
yosys abc -lut $LUT_K -dress
yosys clean
if {!$for_vpr} {yosys techmap -D LUT_K=$LUT_K -map [file dirname [file normalize $argv0]]/cells_map_ff.v}
yosys clean
yosys hierarchy -check
yosys stat

if {$argc > 1} {
        if {$for_vpr} { 
                yosys write_blif [lindex $argv 2] 
        } else { 
                yosys write_json [lindex $argv 2] 
        }
}
