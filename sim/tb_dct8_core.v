// ============================================================================
// tb_dct8_core.v -- self-checking test bench for dct8_core
// ----------------------------------------------------------------------------
// Streams vectors/dct8_<cfg>_stim.hex ({in_valid, in_data} per clock) and
// checks every valid output word against vectors/dct8_<cfg>_expect.hex
// (bit-exact), the in-order index sequence, out_last and the latency of the
// first output.  The vectors include invalid gap blocks, all-extreme corner
// inputs, impulses, image rows and random data.
//
//   iverilog -g2005 -I rtl -P tb_dct8_core.W=14 -o build/tb rtl/*.v sim/tb_dct8_core.v
//   vvp build/tb +stim=vectors/dct8_t1_w14_stim.hex +expect=vectors/dct8_t1_w14_expect.hex
//
// scripts/run_rtl.py runs all configurations with the right parameters.
// ============================================================================
`timescale 1ns/1ps

module tb_dct8_core;
    parameter B_IN      = 8;
    parameter W         = 14;
    parameter G         = 3;
    parameter SS1       = 0;
    parameter SS2       = 0;
    parameter SS3       = 0;
    parameter MR_MODE   = 0;
    parameter STYLE     = 0;
    parameter N_STIM    = 2656;
    parameter N_EXP     = 2608;
    parameter FIRST_OUT = 16;

    reg                   clk, rst, ce, in_valid;
    reg  signed [B_IN-1:0] in_data;
    wire                  out_valid, out_last;
    wire [2:0]            out_index;
    wire signed [W-1:0]   out_data;

    dct8_core #(.B_IN(B_IN), .W(W), .G(G), .SS1(SS1), .SS2(SS2), .SS3(SS3), .MR_MODE(MR_MODE),
                .STYLE(STYLE)) dut (
        .clk(clk), .rst(rst), .ce(ce), .in_valid(in_valid), .in_data(in_data),
        .out_valid(out_valid), .out_index(out_index), .out_last(out_last), .out_data(out_data));

    reg [B_IN:0]    stim [0:N_STIM-1];
    reg [W-1:0]     expv [0:N_EXP-1];
    reg [8*512-1:0] stim_file, exp_file;
    integer         i, n_out, errors;

    initial clk = 1'b0;
    always #5 clk = ~clk;

    // compare whatever the DUT registered at the last rising edge (cycle cyc)
    task check;
        input integer cyc;
        begin
            if (out_valid === 1'b1) begin
                if (n_out == 0 && cyc != FIRST_OUT) begin
                    $display("LATENCY ERROR: first output at cycle %0d, expected %0d", cyc, FIRST_OUT);
                    errors = errors + 1;
                end
                if (n_out >= N_EXP) begin
                    $display("ERROR: unexpected output #%0d at cycle %0d", n_out, cyc);
                    errors = errors + 1;
                end else begin
                    if (out_data !== expv[n_out]) begin
                        if (errors < 10)
                            $display("MISMATCH #%0d (cycle %0d): got %h, expected %h",
                                     n_out, cyc, out_data, expv[n_out]);
                        errors = errors + 1;
                    end
                    if (out_index !== (n_out % 8)) begin
                        $display("INDEX ERROR #%0d: out_index %0d", n_out, out_index);
                        errors = errors + 1;
                    end
                    if (out_last !== ((n_out % 8) == 7)) begin
                        $display("LAST ERROR #%0d", n_out);
                        errors = errors + 1;
                    end
                end
                n_out = n_out + 1;
            end else if (out_valid !== 1'b0) begin
                $display("ERROR: out_valid unknown at cycle %0d", cyc);
                errors = errors + 1;
            end
        end
    endtask

    initial begin
        if (!$value$plusargs("stim=%s", stim_file))
            stim_file = "vectors/dct8_t1_w14_stim.hex";
        if (!$value$plusargs("expect=%s", exp_file))
            exp_file = "vectors/dct8_t1_w14_expect.hex";
        $readmemh(stim_file, stim);
        $readmemh(exp_file, expv);

        rst = 1'b1; ce = 1'b0; in_valid = 1'b0; in_data = {B_IN{1'b0}};
        n_out = 0; errors = 0;
        repeat (4) @(posedge clk);
        @(negedge clk);
        rst = 1'b0;

        // drive on falling edges, the DUT samples on rising edges
        for (i = 0; i < N_STIM; i = i + 1) begin
            check(i);
            ce       = 1'b1;
            in_valid = stim[i][B_IN];
            in_data  = stim[i][B_IN-1:0];
            @(negedge clk);
        end
        check(N_STIM);

        if (n_out != N_EXP) begin
            $display("ERROR: %0d outputs, expected %0d", n_out, N_EXP);
            errors = errors + 1;
        end
        if (errors == 0)
            $display("PASS: dct8_core B_IN=%0d W=%0d G=%0d SS=%0d%0d%0d MR_MODE=%0d STYLE=%0d -- %0d coefficients bit-exact, latency %0d",
                     B_IN, W, G, SS1, SS2, SS3, MR_MODE, STYLE, N_EXP, FIRST_OUT);
        else
            $display("FAIL: dct8_core W=%0d MR_MODE=%0d STYLE=%0d -- %0d errors", W, MR_MODE, STYLE, errors);
        $finish;
    end
endmodule
