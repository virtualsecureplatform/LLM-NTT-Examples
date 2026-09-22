open_project [lindex $argv 0]
open_run impl_1
report_timing_summary -delay_type min_max -report_unconstrained -file linked_timing.rpt
report_utilization -hierarchical -file linked_utilization.rpt
set setup [get_timing_paths -delay_type max -max_paths 1]
set hold [get_timing_paths -delay_type min -max_paths 1]
if {[llength $setup] != 1 || [llength $hold] != 1} { error "Missing linked timing paths" }
set wns [get_property SLACK [lindex $setup 0]]
set whs [get_property SLACK [lindex $hold 0]]
if {$wns < 0 || $whs < 0} { error "Linked design fails timing: setup=$wns hold=$whs" }
set clocks {}
foreach pin [get_pins -hier -filter {REF_PIN_NAME == ap_clk}] {
    if {[regexp {(^|/)product(/|_)} [get_property NAME $pin]]} {
        foreach clk [get_clocks -of_objects $pin] {lappend clocks $clk}
    }
}
set clocks [lsort -unique $clocks]
if {[llength $clocks] == 0} {error "Cannot identify product clock in linked design"}
set expected [lindex $argv 1]
foreach clk $clocks {
    if {abs([get_property PERIOD $clk]-$expected)>0.01} {error "Linked product clock differs from common clock"}
}
set fp [open linked_metrics.json w]
puts $fp "{\"timing_clean\":true,\"wns_ns\":$wns,\"hold_slack_ns\":$whs,\"clock_period_ns\":$expected}"
close $fp
close_project
