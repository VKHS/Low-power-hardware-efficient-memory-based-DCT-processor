// ============================================================================
// cordic2_mr.v -- shared-resource central CORDIC unit (MR-PE)
// ----------------------------------------------------------------------------
// Rotates (u, v) counter-clockwise by ~k*pi/16, k = 1, 2, 3.  ONE unit serves
// all five rotations of a block; its stages are shared by the three angles
// ("one united block in overlapped form") and only the stage options change.
// A rotation by -theta is obtained by the controller by swapping operands and
// results, so the unit itself only rotates counter-clockwise.
//
// MR_MODE = 0 : micro-rotations of the paper (Table 1)
//   stage A : radius scale-up (G guard bits) + exact rotation by
//             P_1 = 10 + j2, P_2 = 50 + j21, P_3 = 50 + j33
//             (shared partial products: 2x, 8x | 48x, 2y | 21y | 33y)
//   stage B : radius scale-down by K_k ~ 1/|P_k| (4 signed powers of two,
//             shifts selected per angle) + round half to even
//   angle error +1.05e-3 / +4.93e-3 / -5.68e-3 rad
//
// MR_MODE = 1 : extended CORDIC-II configuration
//   stage A : guard bits + friend angles (7+j)/8 | (5+5j)/8 + USR 2^-3
//   stage B : USR 2^-5 + nano-rotation + ONE radius scaling
//             K = 1 + 2^-3 - 2^-6 + 2^-8 - 2^-11 + round half to even
//   angle error +2.2e-4 / -1.4e-4 / +3.5e-4 rad (uniform gain)
//
//   k | Table 1  | CORDIC-II: FA   USR3  USR5  n7  n9
//   --+----------+------------------------------------
//   1 | 10 + j2  |            7+j   0    +1   -1   0
//   2 | 50 + j21 |            7+j  +1     0    0  +1
//   3 | 50 + j33 |           5+5j  -1    +1   -1  -1
//
// Bit-exact with python/dct8/cordic2.py.  Latency 2 clocks: the stage-A
// register loads on `issue`, stage B is combinational into the memory write.
// ============================================================================

module cordic2_mr #(
    parameter W       = 14,
    parameter G       = 3,
    parameter MR_MODE = 0,
    parameter STYLE   = 0
) (
    input  wire                clk,
    input  wire                ce,
    input  wire                issue,
    input  wire [1:0]          k,
    input  wire signed [W-1:0] u,
    input  wire signed [W-1:0] v,
    output wire signed [W-1:0] u_out,
    output wire signed [W-1:0] v_out
);
    generate
    if (MR_MODE == 0) begin : g_t1
        // ======================================================== Table 1 mode
        localparam WM = W + G + 8;
        wire signed [WM-1:0] ue = u;
        wire signed [WM-1:0] ve = v;
        wire signed [WM-1:0] x0 = ue <<< G;          // radius scale-up
        wire signed [WM-1:0] y0 = ve <<< G;
        wire k1 = (k == 2'd1);
        wire k2 = (k == 2'd2);
        // shared partial products
        wire signed [WM-1:0] x2  = x0 <<< 1,  y2  = y0 <<< 1;
        wire signed [WM-1:0] x8  = x0 <<< 3,  y8  = y0 <<< 3;
        wire signed [WM-1:0] x48 = (x0 <<< 5) + (x0 <<< 4);
        wire signed [WM-1:0] y48 = (y0 <<< 5) + (y0 <<< 4);
        wire signed [WM-1:0] x21 = (x0 <<< 4) + (x0 <<< 2) + x0;
        wire signed [WM-1:0] y21 = (y0 <<< 4) + (y0 <<< 2) + y0;
        wire signed [WM-1:0] x33 = (x0 <<< 5) + x0;
        wire signed [WM-1:0] y33 = (y0 <<< 5) + y0;
        wire signed [WM-1:0] ax = k1 ? x8 : x48;      // (a - 2) x0
        wire signed [WM-1:0] ay = k1 ? y8 : y48;
        wire signed [WM-1:0] bx = k1 ? x2 : (k2 ? x21 : x33);   // b x0
        wire signed [WM-1:0] by = k1 ? y2 : (k2 ? y21 : y33);
        wire signed [WM-1:0] xa, ya;
        dct8_add3 #(.W(WM), .STYLE(STYLE)) u_xa (.a(x2), .b(ax), .c(by), .nb(1'b0), .nc(1'b1), .y(xa));
        dct8_add3 #(.W(WM), .STYLE(STYLE)) u_ya (.a(bx), .b(y2), .c(ay), .nb(1'b0), .nc(1'b0), .y(ya));

        reg signed [WM-1:0] xr, yr;
        reg        [1:0]    kr;
        always @(posedge clk) begin
            if (ce && issue) begin
                xr <= xa;
                yr <= ya;
                kr <= k;
            end
        end

        // radius scale-down K_k: four signed power-of-two terms; the shift of each
        // term is selected by k BEFORE rounding, so each term is rounded once
        //   term:   t1      t2      t3       t4
        //   k = 1:  +2^-3   -2^-5   +2^-8    +2^-11
        //   k = 2:  +2^-6   +2^-8   -2^-10   -2^-13
        //   k = 3:  +2^-6   +2^-10  +2^-13   -2^-15
        wire q1 = (kr == 2'd1);
        wire q2 = (kr == 2'd2);
        wire signed [WM-1:0] xt1, xt2, xt3, xt4, yt1, yt2, yt3, yt4;
        dct8_rnd_sel #(.W(WM), .SA(3),  .SB(6),  .SC(6))  u_xt1 (.z(xr), .a(q1), .b(q2), .q(xt1));
        dct8_rnd_sel #(.W(WM), .SA(5),  .SB(8),  .SC(10)) u_xt2 (.z(xr), .a(q1), .b(q2), .q(xt2));
        dct8_rnd_sel #(.W(WM), .SA(8),  .SB(10), .SC(13)) u_xt3 (.z(xr), .a(q1), .b(q2), .q(xt3));
        dct8_rnd_sel #(.W(WM), .SA(11), .SB(13), .SC(15)) u_xt4 (.z(xr), .a(q1), .b(q2), .q(xt4));
        dct8_rnd_sel #(.W(WM), .SA(3),  .SB(6),  .SC(6))  u_yt1 (.z(yr), .a(q1), .b(q2), .q(yt1));
        dct8_rnd_sel #(.W(WM), .SA(5),  .SB(8),  .SC(10)) u_yt2 (.z(yr), .a(q1), .b(q2), .q(yt2));
        dct8_rnd_sel #(.W(WM), .SA(8),  .SB(10), .SC(13)) u_yt3 (.z(yr), .a(q1), .b(q2), .q(yt3));
        dct8_rnd_sel #(.W(WM), .SA(11), .SB(13), .SC(15)) u_yt4 (.z(yr), .a(q1), .b(q2), .q(yt4));
        wire n2 = q1;          // t2 negative for k = 1
        wire n3 = q2;          // t3 negative for k = 2
        wire n4 = ~q1;         // t4 negative for k = 2, 3
        wire signed [WM-1:0] xh, yh, xs, ys;
        dct8_add3 #(.W(WM), .STYLE(STYLE)) u_xh (.a(xt1), .b(xt2), .c(xt3), .nb(n2), .nc(n3), .y(xh));
        dct8_add3 #(.W(WM), .STYLE(STYLE)) u_yh (.a(yt1), .b(yt2), .c(yt3), .nb(n2), .nc(n3), .y(yh));
        dct8_add3 #(.W(WM), .STYLE(STYLE)) u_xs (.a(xh), .b(xt4), .c({WM{1'b0}}), .nb(n4), .nc(1'b0), .y(xs));
        dct8_add3 #(.W(WM), .STYLE(STYLE)) u_ys (.a(yh), .b(yt4), .c({WM{1'b0}}), .nb(n4), .nc(1'b0), .y(ys));
        wire signed [WM-1:0] xo, yo;
        dct8_rne #(.W(WM), .S(G)) u_ox (.z(xs), .q(xo));
        dct8_rne #(.W(WM), .S(G)) u_oy (.z(ys), .q(yo));
        assign u_out = xo[W-1:0];
        assign v_out = yo[W-1:0];

    end else begin : g_c2
        // =================================================== CORDIC-II mode
        localparam WM = W + G + 1;
        localparam WP = WM + 3;
        wire signed [WM-1:0] ue = u;
        wire signed [WM-1:0] ve = v;
        wire signed [WP-1:0] x0 = ue <<< G;
        wire signed [WP-1:0] y0 = ve <<< G;
        // friend angles: f = 1 -> (5+5j)/8 (k = 3), f = 0 -> (7+j)/8 (k = 1, 2)
        wire                 f  = (k == 2'd3);
        wire signed [WP-1:0] s  = x0 + y0;
        wire signed [WP-1:0] d  = x0 - y0;
        wire signed [WP-1:0] px = f ? (d <<< 2) : (x0 <<< 3);
        wire signed [WP-1:0] qx = f ? d : s;
        wire signed [WP-1:0] py = f ? (s <<< 2) : (y0 <<< 3);
        wire signed [WP-1:0] qy = f ? s : d;
        wire signed [WP-1:0] fx = f ? (px + qx) : (px - qx);
        wire signed [WP-1:0] fy = py + qy;
        wire signed [WP-1:0] fxr, fyr;
        dct8_rnd #(.W(WP), .S(3)) u_fx (.z(fx), .q(fxr));
        dct8_rnd #(.W(WP), .S(3)) u_fy (.z(fy), .q(fyr));
        wire signed [WM-1:0] x1 = fxr[WM-1:0];
        wire signed [WM-1:0] y1 = fyr[WM-1:0];
        // USR 2^-3: s3 = +1 (k=2), -1 (k=3), 0 (k=1)
        wire s3z = (k == 2'd1);
        wire s3p = (k == 2'd2);
        wire signed [WM-1:0] x1r6, y1r6, x1r2, y1r2;
        dct8_rnd #(.W(WM), .S(6)) u_x1r6 (.z(x1), .q(x1r6));
        dct8_rnd #(.W(WM), .S(6)) u_y1r6 (.z(y1), .q(y1r6));
        dct8_rnd #(.W(WM), .S(2)) u_x1r2 (.z(x1), .q(x1r2));
        dct8_rnd #(.W(WM), .S(2)) u_y1r2 (.z(y1), .q(y1r2));
        wire signed [WM-1:0] x2, y2;
        dct8_add3 #(.W(WM), .STYLE(STYLE)) u_usr3x (
            .a(x1), .b(x1r6), .c(s3z ? {WM{1'b0}} : y1r2), .nb(~s3z), .nc(s3p), .y(x2));
        dct8_add3 #(.W(WM), .STYLE(STYLE)) u_usr3y (
            .a(y1), .b(y1r6), .c(s3z ? {WM{1'b0}} : x1r2), .nb(~s3z), .nc(~s3z & ~s3p), .y(y2));

        reg signed [WM-1:0] x2r, y2r;
        reg        [1:0]    kr;
        always @(posedge clk) begin
            if (ce && issue) begin
                x2r <= x2;
                y2r <= y2;
                kr  <= k;
            end
        end

        // USR 2^-5: s5 = +1 (k=1,3), 0 (k=2)
        wire s5z = (kr == 2'd2);
        wire signed [WM-1:0] x2r10, y2r10, x2r4, y2r4;
        dct8_rnd #(.W(WM), .S(10)) u_x2r10 (.z(x2r), .q(x2r10));
        dct8_rnd #(.W(WM), .S(10)) u_y2r10 (.z(y2r), .q(y2r10));
        dct8_rnd #(.W(WM), .S(4))  u_x2r4  (.z(x2r), .q(x2r4));
        dct8_rnd #(.W(WM), .S(4))  u_y2r4  (.z(y2r), .q(y2r4));
        wire signed [WM-1:0] x3, y3;
        dct8_add3 #(.W(WM), .STYLE(STYLE)) u_usr5x (
            .a(x2r), .b(x2r10), .c(s5z ? {WM{1'b0}} : y2r4), .nb(~s5z), .nc(~s5z), .y(x3));
        dct8_add3 #(.W(WM), .STYLE(STYLE)) u_usr5y (
            .a(y2r), .b(y2r10), .c(s5z ? {WM{1'b0}} : x2r4), .nb(~s5z), .nc(1'b0), .y(y3));
        // nano-rotation: n7 = -1 (k=1,3), n9 = +1 (k=2), -1 (k=3)
        wire n7on  = (kr != 2'd2);
        wire n9on  = (kr == 2'd2) || (kr == 2'd3);
        wire n9neg = (kr == 2'd3);
        wire signed [WM-1:0] x3r7, y3r7, x3r9, y3r9;
        dct8_rnd #(.W(WM), .S(7)) u_x3r7 (.z(x3), .q(x3r7));
        dct8_rnd #(.W(WM), .S(7)) u_y3r7 (.z(y3), .q(y3r7));
        dct8_rnd #(.W(WM), .S(9)) u_x3r9 (.z(x3), .q(x3r9));
        dct8_rnd #(.W(WM), .S(9)) u_y3r9 (.z(y3), .q(y3r9));
        wire signed [WM-1:0] x4, y4;
        dct8_add3 #(.W(WM), .STYLE(STYLE)) u_nanox (
            .a(x3), .b(n7on ? y3r7 : {WM{1'b0}}), .c(n9on ? y3r9 : {WM{1'b0}}),
            .nb(1'b0), .nc(n9on & ~n9neg), .y(x4));
        dct8_add3 #(.W(WM), .STYLE(STYLE)) u_nanoy (
            .a(y3), .b(n7on ? x3r7 : {WM{1'b0}}), .c(n9on ? x3r9 : {WM{1'b0}}),
            .nb(n7on), .nc(n9on & n9neg), .y(y4));
        // radius scaling K = 1 + 2^-3 - 2^-6 + 2^-8 - 2^-11
        wire signed [WM-1:0] x4r3, x4r6, x4r8, x4r11, y4r3, y4r6, y4r8, y4r11;
        dct8_rnd #(.W(WM), .S(3))  u_x4r3  (.z(x4), .q(x4r3));
        dct8_rnd #(.W(WM), .S(6))  u_x4r6  (.z(x4), .q(x4r6));
        dct8_rnd #(.W(WM), .S(8))  u_x4r8  (.z(x4), .q(x4r8));
        dct8_rnd #(.W(WM), .S(11)) u_x4r11 (.z(x4), .q(x4r11));
        dct8_rnd #(.W(WM), .S(3))  u_y4r3  (.z(y4), .q(y4r3));
        dct8_rnd #(.W(WM), .S(6))  u_y4r6  (.z(y4), .q(y4r6));
        dct8_rnd #(.W(WM), .S(8))  u_y4r8  (.z(y4), .q(y4r8));
        dct8_rnd #(.W(WM), .S(11)) u_y4r11 (.z(y4), .q(y4r11));
        wire signed [WM-1:0] x5, y5;
        dct8_add5 #(.W(WM), .STYLE(STYLE)) u_rsx (.a(x4), .b(x4r3), .c(x4r6), .d(x4r8), .e(x4r11), .y(x5));
        dct8_add5 #(.W(WM), .STYLE(STYLE)) u_rsy (.a(y4), .b(y4r3), .c(y4r6), .d(y4r8), .e(y4r11), .y(y5));
        wire signed [WM-1:0] x6, y6;
        dct8_rne #(.W(WM), .S(G)) u_ox (.z(x5), .q(x6));
        dct8_rne #(.W(WM), .S(G)) u_oy (.z(y5), .q(y6));
        assign u_out = x6[W-1:0];
        assign v_out = y6[W-1:0];
    end
    endgenerate
endmodule
