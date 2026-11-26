// ============================================================================
// tb_dct2d_8x8.v -- self-checking test bench for the 8x8 2-D DCT processor
// ----------------------------------------------------------------------------
// Streams 8x8 blocks (row-major pixels, level-shifted) and checks the 2-D
// coefficients, which leave column by column (out_u = u, out_v = v), against
// vectors/dct2d_t1_expect.hex, bit for bit.
//
//   iverilog -g2005 -I rtl -o build/tb2d rtl/*.v sim/tb_dct2d_8x8.v
//   vvp build/tb2d +stim=vectors/dct2d_t1_stim.hex +expect=vectors/dct2d_t1_expect.hex
// ============================================================================
`timescale 1ns/1ps

module tb_dct2d_8x8;
    parameter B_IN      = 8;
    parameter W_ROW     = 14;
    parameter G_ROW     = 3;
    parameter SS1_ROW   = 0;
    parameter SS2_ROW   = 0;
    parameter SS3_ROW   = 0;
    parameter W_COL     = 16;
    parameter G_COL     = 3;
    parameter SS1_COL   = 1;
    parameter SS2_COL   = 1;
    parameter SS3_COL   = 1;
    parameter OUT_W     = 12;
    parameter OUT_FRAC  = 0;
    parameter MR_MODE   = 0;
    parameter STYLE     = 0;
    parameter N_STIM    = 2440;
    parameter N_EXP     = 2240;
    parameter FIRST_OUT = 97;

    reg                    clk, rst, ce, in_valid;
    reg  signed [B_IN-1:0] in_data;
    wire                   out_valid;
    wire [2:0]             out_u, out_v;
    wire signed [OUT_W-1:0] out_data;

    dct2d_8x8 #(.B_IN(B_IN), .W_ROW(W_ROW), .G_ROW(G_ROW), .SS1_ROW(SS1_ROW), .SS2_ROW(SS2_ROW),
                .SS3_ROW(SS3_ROW), .W_COL(W_COL), .G_COL(G_COL), .SS1_COL(SS1_COL),
                .SS2_COL(SS2_COL), .SS3_COL(SS3_COL), .OUT_W(OUT_W), .OUT_FRAC(OUT_FRAC),
                .MR_MODE(MR_MODE), .STYLE(STYLE)) dut (
        .clk(clk), .rst(rst), .ce(ce), .in_valid(in_valid), .in_data(in_data),
        .out_valid(out_valid), .out_u(out_u), .out_v(out_v), .out_data(out_data));

    reg [B_IN:0]    stim [0:N_STIM-1];
    reg [OUT_W-1:0] expv [0:N_EXP-1];
    reg [8*512-1:0] stim_file, exp_file;
    integer         i, n_out, errors;

    initial clk = 1'b0;
    always #5 clk = ~clk;

    task check;
        input integer cyc;
        begin
            if (out_valid === 1'b1) begin
                if (n_out == 0 && cyc != FIRST_OUT) begin
                    $display("LATENCY ERROR: first output at cycle %0d, expected %0d", cyc, FIRST_OUT);
                    errors = errors + 1;
                end
                if (n_out < N_EXP) begin
                    if (out_data !== expv[n_out]) begin
                        if (errors < 10)
                            $display("MISMATCH #%0d (cycle %0d, u=%0d v=%0d): got %h, expected %h",
                                     n_out, cyc, out_u, out_v, out_data, expv[n_out]);
                        errors = errors + 1;
                    end
                    if (out_u !== (n_out % 8) || out_v !== ((n_out / 8) % 8)) begin
                        $display("INDEX ERROR #%0d: u=%0d v=%0d", n_out, out_u, out_v);
                        errors = errors + 1;
                    end
                end else begin
                    $display("ERROR: unexpected output #%0d", n_out);
                    errors = errors + 1;
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
            stim_file = "vectors/dct2d_t1_stim.hex";
        if (!$value$plusargs("expect=%s", exp_file))
            exp_file = "vectors/dct2d_t1_expect.hex";
        $readmemh(stim_file, stim);
        $readmemh(exp_file, expv);

        rst = 1'b1; ce = 1'b0; in_valid = 1'b0; in_data = {B_IN{1'b0}};
        n_out = 0; errors = 0;
        repeat (4) @(posedge clk);
        @(negedge clk);
        rst = 1'b0;

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
            $display("PASS: dct2d_8x8 W_ROW=%0d W_COL=%0d MR_MODE=%0d STYLE=%0d -- %0d coefficients bit-exact, latency %0d",
                     W_ROW, W_COL, MR_MODE, STYLE, N_EXP, FIRST_OUT);
        else
            $display("FAIL: dct2d_8x8 MR_MODE=%0d STYLE=%0d -- %0d errors", MR_MODE, STYLE, errors);
        $finish;
    end
endmodule
