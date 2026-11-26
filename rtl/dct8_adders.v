// ============================================================================
// dct8_adders.v -- carry-save / carry-lookahead building blocks and the
//                  multi-operand adders of the CORDIC-II micro-rotation unit
// ----------------------------------------------------------------------------
// STYLE = 0 : behavioural "+" (lets FPGA tools map onto carry chains)
// STYLE = 1 : explicit 3:2 / 4:2 carry-save compression + Kogge-Stone CLA
//             (ASIC style, one carry-propagate adder per multi-operand sum)
// Both styles compute the same sum modulo 2^W, bit for bit.
// Negated operands are formed as ~x with the "+1" injected into a free
// carry-save LSB or the CLA carry-in, so subtraction costs no extra adder.
// ============================================================================

// ---------------------------------------------------------------- 3:2 CSA
module csa_3to2 #(
    parameter W = 16
) (
    input  wire [W-1:0] a,
    input  wire [W-1:0] b,
    input  wire [W-1:0] c,
    input  wire         cin,      // enters the free LSB of the carry vector
    output wire [W-1:0] sum,
    output wire [W-1:0] carry
);
    wire [W-1:0] maj = (a & b) | (a & c) | (b & c);
    assign sum   = a ^ b ^ c;
    assign carry = {maj[W-2:0], cin};
endmodule

// ---------------------------------------------------------------- 4:2 CSA
// a + b + c + d + cin0 + cin1 == sum + carry   (mod 2^W)
module csa_4to2 #(
    parameter W = 16
) (
    input  wire [W-1:0] a,
    input  wire [W-1:0] b,
    input  wire [W-1:0] c,
    input  wire [W-1:0] d,
    input  wire         cin0,
    input  wire         cin1,
    output wire [W-1:0] sum,
    output wire [W-1:0] carry
);
    wire [W-1:0] s1, c1;
    csa_3to2 #(.W(W)) u_l1 (.a(a),  .b(b),  .c(c), .cin(cin0), .sum(s1),  .carry(c1));
    csa_3to2 #(.W(W)) u_l2 (.a(s1), .b(c1), .c(d), .cin(cin1), .sum(sum), .carry(carry));
endmodule

// ---------------------------------------------------- Kogge-Stone CLA adder
module cla_adder #(
    parameter W = 16
) (
    input  wire [W-1:0] a,
    input  wire [W-1:0] b,
    input  wire         cin,
    output wire [W-1:0] s
);
    reg [W-1:0] g, p, gn, pn, c;
    integer i, d;
    always @(*) begin
        g = a & b;
        p = a ^ b;
        // fold the carry-in into bit 0 generate
        g[0] = (a[0] & b[0]) | (p[0] & cin);
        for (d = 1; d < W; d = d * 2) begin
            gn = g;
            pn = p;
            for (i = 0; i < W; i = i + 1) begin
                if (i >= d) begin
                    gn[i] = g[i] | (p[i] & g[i-d]);
                    pn[i] = p[i] & p[i-d];
                end
            end
            g = gn;
            p = pn;
        end
        c = {g[W-2:0], cin};       // carry into each bit
    end
    assign s = a ^ b ^ c;
endmodule

// ------------------------------------------------- y = a +/- b +/- c (mod 2^W)
module dct8_add3 #(
    parameter W     = 16,
    parameter STYLE = 0
) (
    input  wire signed [W-1:0] a,
    input  wire signed [W-1:0] b,
    input  wire signed [W-1:0] c,
    input  wire                nb,    // 1: subtract b
    input  wire                nc,    // 1: subtract c
    output wire signed [W-1:0] y
);
    generate
        if (STYLE == 0) begin : g_beh
            wire signed [W-1:0] bb = nb ? -b : b;
            wire signed [W-1:0] cc = nc ? -c : c;
            assign y = a + bb + cc;
        end else begin : g_csa
            wire [W-1:0] bx = b ^ {W{nb}};
            wire [W-1:0] cx = c ^ {W{nc}};
            wire [W-1:0] s, k;
            csa_3to2  #(.W(W)) u_csa (.a(a), .b(bx), .c(cx), .cin(nb), .sum(s), .carry(k));
            cla_adder #(.W(W)) u_cla (.a(s), .b(k), .cin(nc), .s(y));
        end
    endgenerate
endmodule

// --------------------------------- radius scaling y = a + b - c + d - e (mod 2^W)
module dct8_add5 #(
    parameter W     = 16,
    parameter STYLE = 0
) (
    input  wire signed [W-1:0] a,
    input  wire signed [W-1:0] b,
    input  wire signed [W-1:0] c,
    input  wire signed [W-1:0] d,
    input  wire signed [W-1:0] e,
    output wire signed [W-1:0] y
);
    generate
        if (STYLE == 0) begin : g_beh
            assign y = a + b - c + d - e;
        end else begin : g_csa
            wire [W-1:0] s4, k4, s5, k5;
            // 4:2 compressor: a + b + ~c + d + 1 (the 1 completes -c)
            csa_4to2  #(.W(W)) u_c42 (.a(a), .b(b), .c(~c), .d(d), .cin0(1'b1), .cin1(1'b1),
                                      .sum(s4), .carry(k4));
            // the second free LSB above already carries the +1 that completes -e
            csa_3to2  #(.W(W)) u_c32 (.a(s4), .b(k4), .c(~e), .cin(1'b0), .sum(s5), .carry(k5));
            cla_adder #(.W(W)) u_cla (.a(s5), .b(k5), .cin(1'b0), .s(y));
        end
    endgenerate
endmodule
