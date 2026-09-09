# Give OOC primary inputs a physical internal route for hold repair.
# Identity LUTs preserve the interface and count in reported utilization.
set input_hold_index 0
set input_hold_map [open [file join $out_dir input_hold_buffers.txt] w]
set input_hold_ports [get_ports -filter {DIRECTION == IN}]
set input_hold_ports [lsearch -all -inline -not -exact $input_hold_ports $clock_port]
for {set input_hold_stage 0} {$input_hold_stage < [lindex $argv 21]} {incr input_hold_stage} {
foreach input_hold_port [lsort $input_hold_ports] {
    set input_hold_old [get_nets -of_objects $input_hold_port]
    if {[llength $input_hold_old] == 0} {continue}
    if {[llength $input_hold_old] != 1} {error "Expected one net per input bit"}
    set input_hold_cell ntt_input_hold_$input_hold_index
    set input_hold_net ntt_input_hold_net_$input_hold_index
    create_cell -reference LUT1 $input_hold_cell
    set_property INIT 2'h2 [get_cells $input_hold_cell]
    set_property DONT_TOUCH true [get_cells $input_hold_cell]
    create_net $input_hold_net
    disconnect_net -net $input_hold_old -objects $input_hold_port
    connect_net -net $input_hold_old -objects [get_pins $input_hold_cell/O]
    connect_net -net [get_nets $input_hold_net] -objects [concat $input_hold_port [get_pins $input_hold_cell/I0]]
    puts $input_hold_map "$input_hold_port $input_hold_cell"
    incr input_hold_index
}
}
close $input_hold_map
puts "Inserted $input_hold_index input identity LUTs for physical hold repair"
