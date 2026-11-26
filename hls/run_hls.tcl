# ============================================================================
# run_hls.tcl -- Vitis HLS flow: C simulation, synthesis, (co-simulation), IP
# ----------------------------------------------------------------------------
#   vitis_hls -f hls/run_hls.tcl                                  # dct8_cycle_top
#   vitis_hls -f hls/run_hls.tcl -tclargs dct8_block_top
#   vitis_hls -f hls/run_hls.tcl -tclargs dct2d_top xc7a25tcsg325-1 6.9
# Default target: Artix-7 XC7A25T (the device of the paper), 6.9 ns (145 MHz).
# The configuration is set by the macros at the top of hls/src/dct8_hls.h
# (default: B_IN 8, W 14, G 3, SS 000, Table 1 micro-rotations), which match
# vectors/dct8_t1_w14 and vectors/dct2d_t1 used by the C test benches.
# ============================================================================
set here   [file dirname [file normalize [info script]]]
set root   [file dirname $here]
set top    dct8_cycle_top
set part   xc7a25tcsg325-1
set period 6.9
if {[info exists argv]} {
    if {[llength $argv] >= 1} { set top    [lindex $argv 0] }
    if {[llength $argv] >= 2} { set part   [lindex $argv 1] }
    if {[llength $argv] >= 3} { set period [lindex $argv 2] }
}
set cflags "-I$root/hls/src"

open_project -reset build_hls_$top
set_top $top
add_files $root/hls/src/dct8_top.cpp -cflags $cflags
if {$top eq "dct2d_top"} {
    add_files -tb $root/hls/tb/tb_dct2d.cpp -cflags "$cflags -I$root/hls/tb"
    set tbargs "$root/vectors dct2d_t1"
} else {
    add_files -tb $root/hls/tb/tb_dct8.cpp -cflags "$cflags -I$root/hls/tb"
    set tbargs "$root/vectors dct8_t1_w14"
}
open_solution -reset sol1 -flow_target vivado
set_part $part
create_clock -period $period -name default

csim_design -argv $tbargs
csynth_design
# cosim_design -argv $tbargs -trace_level none
export_design -format ip_catalog
exit
