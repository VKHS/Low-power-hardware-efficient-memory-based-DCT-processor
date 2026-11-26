// ============================================================================
// dct8_round.v -- rounding right shifts used throughout the datapath
// ----------------------------------------------------------------------------
// dct8_rnd : round half up,      q = floor((z + 2^(S-1)) / 2^S)
//            = (z >>> S) + z[S-1]          (discarded MSB re-enters as carry)
// dct8_rne : round half to even, q = (z >>> S) + (z[S-1] & (z[S] | |z[S-2:0]))
//            (no bias build-up; used for safe scaling and final rounding)
// dct8_rnd_sel : round half up by one of three shifts, selected before the
//                rounding: a ? rnd(z, SA) : b ? rnd(z, SB) : rnd(z, SC)
// They are exactly the primitives rnd() / rne() of python/dct8/fixedpoint.py
// (the SS units use von Neumann rounding, see dct8_bf_pe.v).
// Requires 1 <= S <= W-1.
// ============================================================================

module dct8_rnd #(
    parameter W = 16,
    parameter S = 1
) (
    input  wire signed [W-1:0] z,
    output wire signed [W-1:0] q
);
    wire signed [W-1:0] sh  = z >>> S;
    wire signed [W-1:0] inc = $signed({{(W-1){1'b0}}, z[S-1]});
    assign q = sh + inc;
endmodule


module dct8_rne #(
    parameter W = 16,
    parameter S = 1
) (
    input  wire signed [W-1:0] z,
    output wire signed [W-1:0] q
);
    localparam [W-1:0] LOWMASK = (S > 1) ? ((1 << (S - 1)) - 1) : 0;
    wire signed [W-1:0] sh    = z >>> S;
    wire                half  = z[S-1];
    wire                stick = |(z & LOWMASK);
    wire                odd   = z[S];
    wire                up    = half & (stick | odd);
    wire signed [W-1:0] inc   = $signed({{(W-1){1'b0}}, up});
    assign q = sh + inc;
endmodule


module dct8_rnd_sel #(
    parameter W  = 16,
    parameter SA = 1,
    parameter SB = 1,
    parameter SC = 1
) (
    input  wire signed [W-1:0] z,
    input  wire                a,
    input  wire                b,
    output wire signed [W-1:0] q
);
    wire signed [W-1:0] sh  = a ? (z >>> SA) : (b ? (z >>> SB) : (z >>> SC));
    wire                rb  = a ? z[SA-1] : (b ? z[SB-1] : z[SC-1]);
    wire signed [W-1:0] inc = $signed({{(W-1){1'b0}}, rb});
    assign q = sh + inc;
endmodule
