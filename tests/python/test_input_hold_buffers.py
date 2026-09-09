"""Check physical input buffering preserves connectivity, including reset."""
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[2]


class InputHoldBuffers(unittest.TestCase):
    def test_identity_chains_leave_clock_and_consumers_connected(self):
        self.assertIsNotNone(shutil.which('tclsh'))
        with tempfile.TemporaryDirectory() as tmp:
            script = r'''
set clock_port clock
set out_dir [lindex $argv 0]
set helper [lindex $argv 1]
set argv [lrepeat 22 {}]
lset argv 21 2
array set nets {clock_net {clock reg/C} data_net {data reg/D other/D} reset_net {reset reg/R}}
array set properties {}
proc get_ports {args} {return {clock data reset unused}}
proc get_nets {args} {
    global nets
    if {[lindex $args 0] ne "-of_objects"} {return [lindex $args 0]}
    set result {}
    foreach name [array names nets] {
        if {[lsearch -exact $nets($name) [lindex $args 1]] >= 0} {lappend result $name}
    }
    return $result
}
proc create_cell {args} {
    if {[lindex $args 1] ne "LUT1"} {error "non-identity primitive"}
}
proc get_cells {name} {return $name}
proc get_pins {name} {return $name}
proc set_property {key value cell} {global properties; set properties($cell,$key) $value}
proc create_net {name} {global nets; set nets($name) {}}
proc disconnect_net {args} {
    global nets
    set name [lindex $args 1]
    foreach pin [lindex $args 3] {
        set i [lsearch -exact $nets($name) $pin]
        if {$i < 0} {error "missing pin"}
        set nets($name) [lreplace $nets($name) $i $i]
    }
}
proc connect_net {args} {
    global nets
    foreach pin [lindex $args 3] {
        if {[llength [get_nets -of_objects $pin]]} {error "pin connected twice"}
        lappend nets([lindex $args 1]) $pin
    }
}
source $helper
if {$nets(clock_net) ne {clock reg/C}} {error "clock changed"}
if {$input_hold_index != 4} {error "wrong buffer count"}
foreach {port endpoints} {data {reg/D other/D} reset {reg/R}} {
    set net [get_nets -of_objects $port]
    for {set stage 0} {$stage < 2} {incr stage} {
        set inputs [lsearch -all -inline -glob $nets($net) */I0]
        if {[llength $inputs] != 1} {error "broken chain"}
        set cell [string range [lindex $inputs 0] 0 end-3]
        if {$properties($cell,INIT) ne "2'h2" || $properties($cell,DONT_TOUCH) ne "true"} {
            error "not a preserved identity"
        }
        set net [get_nets -of_objects $cell/O]
    }
    foreach pin $endpoints {
        if {[lsearch -exact $nets($net) $pin] < 0} {error "consumer disconnected"}
    }
}
'''
            path = Path(tmp) / 'check.tcl'
            path.write_text(script)
            subprocess.run(['tclsh', str(path), tmp,
                            str(ROOT / 'scripts/insert_input_hold_buffers.tcl')],
                           check=True, capture_output=True, text=True)

    def test_reject_invalid_stage_counts(self):
        from architecture_search.hardware import _evaluate
        with tempfile.TemporaryDirectory() as tmp:
            for value in (True, 0, 5, 1.5, '2'):
                with self.subTest(value=value), self.assertRaises(ValueError):
                    _evaluate(Path(tmp)/'unused.sv', 'top',
                              {'input_hold_buffer_stages': value}, {},
                              Path(tmp)/'route', 'route', 1)
