source $::env(SCRIPTS_DIR)/openroad/common/io.tcl
read_pnr_libs
read_lefs
read_current_netlist

foreach lib $::libs {
    set current_sites [$lib getSites]
    foreach site $current_sites {
        set name [$site getName]
        set ::sites($name) $site
    }
}

set ::default_site $::sites($::env(PLACE_SITE))

set ::default_site_height [expr [$::default_site getHeight] / double($::dbu)]
set ::default_site_width [expr [$::default_site getWidth] / double($::dbu)]

puts "%OL_METRIC pdk__site_height $::default_site_height"
puts "%OL_METRIC pdk__site_width $::default_site_width"
