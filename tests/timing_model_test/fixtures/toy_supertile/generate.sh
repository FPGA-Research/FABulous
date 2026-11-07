#!/usr/bin/env bash
# Regenerate the toy supertile fixture from rtl.v, run from the repository root
# inside the Nix shell: tests/timing_model_test/fixtures/toy_supertile/generate.sh
# <ihp-sg13g2 PDK directory>.
#
# synth.v / synth.sdf: the timing model's own synthesis and OpenSTA SDF.
# layout.v / layout.spef / layout.sdf: LibreLane's synthesis pass order with the
# members kept (SYNTH_KEEP_HIERARCHY_MODULES), an OpenROAD flat link and
# placement whose estimated parasitics give non-zero wire delays, and OpenSTA's
# SDF of that netlist with the SPEF read back.
set -euo pipefail
pdk=$(realpath "$1")
here=$(dirname "$(realpath "$0")")
lib="$pdk/libs.ref/sg13g2_stdcell/lib/sg13g2_stdcell_typ_1p20V_25C.lib"
lef="$pdk/libs.ref/sg13g2_stdcell/lef"
work=$(mktemp -d)
trap 'rm -rf "$work"' EXIT
rm -f "$here"/{synth.v,synth.sdf,layout.v,layout.spef,layout.sdf}

uv run --frozen python - "$here" "$pdk" <<'PY'
import sys
from pathlib import Path

from fabulous.tools.opensta import OpenStaTool
from fabulous.tools.yosys import YosysTool

here, pdk = Path(sys.argv[1]), Path(sys.argv[2])
lib = pdk / "libs.ref/sg13g2_stdcell/lib/sg13g2_stdcell_typ_1p20V_25C.lib"
maps = pdk / "libs.tech/librelane/sg13g2_stdcell"
YosysTool.synthesize_gate_level(
    verilog_files=[here / "rtl.v"],
    liberty_files=[lib],
    top_name="TOY",
    netlist_file=here / "synth.v",
    techmap_files=[maps / "latch_map.v", maps / "tribuff_map.v"],
    tiehi_cell_and_port=None,
    tielo_cell_and_port=None,
    min_buf_cell_and_ports="sg13g2_buf_1 A X",
)
OpenStaTool.write_sdf(
    netlist_file=here / "synth.v",
    liberty_files=[lib],
    top_name="TOY",
    spef_files=[],
    sdf_file=here / "synth.sdf",
)
PY

yosys -q -p "
read_liberty -lib $lib
read_verilog -sv $here/rtl.v
hierarchy -check -top TOY
proc
setattr -mod -set keep_hierarchy 1 TOY_top TOY_bot
flatten
opt
techmap
opt
abc -liberty $lib
opt_clean -purge
setundef -zero
splitnets
opt_clean -purge
insbuf -buf sg13g2_buf_1 A X
write_verilog -noattr -noexpr -nohex -nodec $work/keep.v
"

openroad -no_splash -exit /dev/stdin <<TCL
read_lef $lef/sg13g2_tech.lef
read_lef $lef/sg13g2_stdcell.lef
read_liberty $lib
read_verilog $work/keep.v
link_design TOY
initialize_floorplan -die_area {0 0 400 400} -core_area {10 10 390 390} -site CoreSite
make_tracks
place_pins -hor_layers Metal3 -ver_layers Metal2
global_placement -density 0.05
detailed_placement
set_wire_rc -signal -resistance 0.1 -capacitance 0.002
estimate_parasitics -placement -spef_file $here/layout.spef
write_verilog $here/layout.v
TCL

sta -no_splash -exit /dev/stdin <<TCL
read_liberty $lib
read_verilog $here/layout.v
link_design TOY
read_spef $here/layout.spef
write_sdf $here/layout.sdf
TCL

# svlint wants indentation in steps of 4 spaces; Yosys writes 2, OpenROAD 1.
for netlist in "$here/synth.v" "$here/layout.v"; do
  awk '{ match($0, /^ */); printf "%*s%s\n", 4 * int((RLENGTH + 1) / 2), "", substr($0, RLENGTH + 1) }' \
    "$netlist" >"$work/indented.v"
  mv "$work/indented.v" "$netlist"
done
# OpenROAD ends the SPEF with a blank line.
sed -i -e '${/^$/d}' "$here/layout.spef"
