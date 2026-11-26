# ============================================================================
# vivado_synth.tcl -- out-of-context synthesis + implementation of the RTL
# ----------------------------------------------------------------------------
#   vivado -mode batch -source scripts/vivado_synth.tcl
#   vivado -mode batch -source scripts/vivado_synth.tcl -tclargs dct8_core 14 0 6.9
#   vivado -mode batch -source scripts/vivado_synth.tcl -tclargs dct2d_8x8 14 1 7.5
# Arguments: top (dct8_core | dct2d_8x8), W (dct8_core) or W_ROW (dct2d_8x8, with
# W_COL = W_ROW + 2), MR_MODE (0 Table 1, 1 CORDIC-II), clock period in ns.
# Part: Artix-7 XC7A25T (the device of the paper).
# Reports (utilization, timing, power with default activity) go to build/vivado_<top>/.
# ============================================================================
set root   [file dirname [file dirname [file normalize [info script]]]]
set top    dct8_core
set w      14
set mode   0
set period 6.9
if {[llength $argv] >= 1} { set top    [lindex $argv 0] }
if {[llength $argv] >= 2} { set w      [lindex $argv 1] }
if {[llength $argv] >= 3} { set mode   [lindex $argv 2] }
if {[llength $argv] >= 4} { set period [lindex $argv 3] }
set part xc7a25tcsg325-1
set out  $root/build/vivado_${top}_w${w}_m${mode}
file mkdir $out

read_verilog [glob $root/rtl/*.v]
# word lengths below 11 bits need safe scaling (headroom H = 3 - SS1 - SS2 - SS3)
set ss [expr {$w < 11 ? 1 : 0}]
if {$top eq "dct8_core"} {
    set generics [list W=$w MR_MODE=$mode SS1=$ss SS2=$ss SS3=$ss]
} else {
    set generics [list W_ROW=$w W_COL=[expr {$w + 2}] MR_MODE=$mode \
                       SS1_ROW=$ss SS2_ROW=$ss SS3_ROW=$ss]
}
set gopts {}
foreach g $generics { lappend gopts -generic $g }
synth_design -top $top -part $part -include_dirs $root/rtl -mode out_of_context {*}$gopts
create_clock -name clk -period $period [get_ports clk]
opt_design
place_design
route_design
report_utilization    -file $out/utilization.rpt
report_timing_summary -file $out/timing.rpt
report_power          -file $out/power.rpt
puts "reports written to $out"
