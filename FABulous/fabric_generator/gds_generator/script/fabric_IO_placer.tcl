source $::env(SCRIPTS_DIR)/openroad/common/io.tcl
read_current_odb

dict for {pin_name values} $::env(FABULOUS_MANUAL_PINS) {
    set layer [lindex $values 0]
    set x [lindex $values 1]
    set y [lindex $values 2]
    set width [lindex $values 3]
    set height [lindex $values 4]
    puts "\[INFO\] Placing manual I/O $pin_name using layer $layer at ($x, $y) size ($width, $height)"

    log_cmd place_pin \
        -pin_name $pin_name \
        -layer $layer \
        -location [list $x $y] \
        -pin_size [list $width $height] \
        -force_to_die_boundary

    #-placed_status


}

write_views

report_design_area_metrics
