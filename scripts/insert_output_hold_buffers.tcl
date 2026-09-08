# Identity LUTs give the router a real data path at an OOC output boundary.
# Apply after synthesis, before placement. The added LUTs remain in utilization.
set output_hold_index 0
set output_hold_map [open [file join $out_dir output_hold_buffers.txt] w]
for {set output_hold_stage 0} {$output_hold_stage < [lindex $argv 19]} {incr output_hold_stage} {
foreach output_hold_port [lsort [all_outputs]] {
    set output_hold_old [get_nets -of_objects $output_hold_port]
    if {[llength $output_hold_old] != 1} {error "Expected one driver net per output bit"}
    set output_hold_cell ntt_output_hold_$output_hold_index
    set output_hold_net ntt_output_hold_net_$output_hold_index
    create_cell -reference LUT1 $output_hold_cell
    set_property INIT 2'h2 [get_cells $output_hold_cell]
    set_property DONT_TOUCH true [get_cells $output_hold_cell]
    create_net $output_hold_net
    disconnect_net -net $output_hold_old -objects $output_hold_port
    connect_net -net $output_hold_old -objects [get_pins $output_hold_cell/I0]
    connect_net -net [get_nets $output_hold_net] -objects [concat [get_pins $output_hold_cell/O] $output_hold_port]
    puts $output_hold_map "$output_hold_port $output_hold_cell"
    incr output_hold_index
}
}
close $output_hold_map
puts "Inserted $output_hold_index output identity LUTs for physical hold repair"
