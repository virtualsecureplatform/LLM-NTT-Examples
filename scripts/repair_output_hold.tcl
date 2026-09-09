# Incremental physical repair of negative output hold paths only.
# Existing cells keep their exact placement; no timing exception is introduced.
open_checkpoint [lindex $argv 0]
set out_dir [lindex $argv 1]
set max_passes [lindex $argv 2]
set existing [get_cells -hier -filter {IS_PRIMITIVE && LOC != "" && BEL != ""}]
set_property IS_LOC_FIXED true $existing
# Expanded DSP48E2 subcells share one site; fixing their individual BELs
# conflicts in Vivado 2023.2. Their site remains fixed by IS_LOC_FIXED.
set ordinary [filter $existing {REF_NAME !~ DSP*}]
set_property IS_BEL_FIXED true $ordinary
set map [open [file join $out_dir output_hold_repairs.txt] w]
set index 0
for {set pass 0} {$pass < $max_passes} {incr pass} {
    set paths [get_timing_paths -delay_type min -slack_lesser_than 0 -max_paths 10000 -nworst 1 -to [all_outputs]]
    set ports {}
    foreach path $paths {
        set port [get_ports -quiet [get_property ENDPOINT_PIN $path]]
        if {[llength $port] != 1} {error "Hold endpoint is not one output port"}
        lappend ports $port
    }
    set ports [lsort -unique $ports]
    if {![llength $ports]} {break}
    foreach port $ports {
        set old [get_nets -of_objects $port]
        if {[llength $old] != 1} {error "Expected one output net"}
        set cell ntt_output_eco_$index
        set net ntt_output_eco_net_$index
        create_cell -reference LUT1 $cell
        set_property INIT 2'h2 [get_cells $cell]
        set_property DONT_TOUCH true [get_cells $cell]
        create_net $net
        disconnect_net -net $old -objects $port
        connect_net -net $old -objects [get_pins $cell/I0]
        connect_net -net [get_nets $net] -objects [concat [get_pins $cell/O] $port]
        puts $map "$pass $port $cell"
        incr index
    }
    flush $map
    # Vivado uses incremental placement for an edited, already placed design.
    place_design
    route_design -preserve
}
close $map
report_route_status -file [file join $out_dir route_status.rpt]
report_utilization -file [file join $out_dir utilization_route.rpt]
report_timing_summary -delay_type min_max -max_paths 20 -file [file join $out_dir timing_summary_route.rpt]
set fp [open [file join $out_dir timing.properties] w]
foreach {kind name} {max wns_ns min hold_slack_ns} {
    set path [get_timing_paths -delay_type $kind -max_paths 1 -nworst 1]
    if {[llength $path] != 1} {error "Missing timing path"}
    puts $fp "$name=[get_property SLACK [lindex $path 0]]"
}
puts $fp "added_output_luts=$index"
close $fp
write_checkpoint -force [file join $out_dir repaired_route.dcp]
