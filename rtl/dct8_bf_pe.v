// ============================================================================
// dct8_bf_pe.v -- radix-2 butterfly datapath with its safe-scaling (SS) unit
// ----------------------------------------------------------------------------
//   sum  = a + b        diff = a - b          (W+1 bits, then W bits)
//   scale = 1 : both outputs are divided by 2 with von Neumann rounding
//               (round half to odd): q = (z >>> 1) | z[0] -- the discarded
//               bit is OR-ed into the LSB, no adder.  Unbiased, and it never
//               rounds 2^(W-1) - 1/2 up to 2^(W-1), so the SS unit cannot
//               overflow.
// The butterfly unit has two of these datapaths (BF0, BF1).
// ============================================================================

module dct8_bf_pe #(
    parameter W = 12
) (
    input  wire signed [W-1:0] a,
    input  wire signed [W-1:0] b,
    input  wire                scale,
    output wire signed [W-1:0] sum,
    output wire signed [W-1:0] diff
);
    wire signed [W:0] s = a + b;      // W+1 bits: no overflow before scaling
    wire signed [W:0] d = a - b;
    wire [W-1:0] sh = {s[W:2], s[1] | s[0]};
    wire [W-1:0] dh = {d[W:2], d[1] | d[0]};
    assign sum  = scale ? sh : s[W-1:0];
    assign diff = scale ? dh : d[W-1:0];
endmodule
