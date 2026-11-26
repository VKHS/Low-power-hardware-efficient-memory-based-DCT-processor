// ============================================================================
// dct2d_8x8.v -- 8x8 2-D DCT from two memory-based 1-D processors
// ----------------------------------------------------------------------------
//   pixels (row-major) -> dct8_core (rows) -> dct8_transpose -> dct8_core (columns)
//                      -> round half to even -> out_data
//
// Input : 8x8 blocks, row-major, one sample per clock, signed B_IN bits
//         (e.g. level-shifted 8-bit pixels).  Gaps must be whole blocks.
// Output: X[u][v] of the orthonormal 2-D DCT-II with OUT_FRAC fractional bits,
//         emitted column by column: X[0][v] .. X[7][v] for v = 0..7
//         (out_u = u, out_v = v).
// Scaling: each pass carries the post-scaling factor 2*sqrt(2); together they
//          give (2 sqrt 2)^2 = 8, so the column output is 2^(E_ROW+E_COL+3) X2D
//          and the final stage only shifts: round half to even by OUT_SHIFT
//          bits, or an exact left shift when OUT_SHIFT <= 0 (short WLs).
// Latency: first coefficient 97 clocks after the first pixel.
// ============================================================================

module dct2d_8x8 #(
    parameter B_IN      = 8,
    parameter W_ROW     = 14,
    parameter G_ROW     = 3,
    parameter SS1_ROW   = 0,
    parameter SS2_ROW   = 0,
    parameter SS3_ROW   = 0,
    parameter W_COL     = 16,
    parameter G_COL     = 3,
    parameter SS1_COL   = 1,
    parameter SS2_COL   = 1,
    parameter SS3_COL   = 1,
    parameter OUT_W     = 12,
    parameter OUT_FRAC  = 0,
    parameter MR_MODE   = 0,
    parameter STYLE     = 0
) (
    input  wire                     clk,
    input  wire                     rst,
    input  wire                     ce,
    input  wire                     in_valid,
    input  wire signed [B_IN-1:0]   in_data,
    output reg                      out_valid,
    output reg  [2:0]               out_u,
    output reg  [2:0]               out_v,
    output reg  signed [OUT_W-1:0]  out_data
);
    localparam SS_ROW = SS1_ROW + SS2_ROW + SS3_ROW;
    localparam SS_COL = SS1_COL + SS2_COL + SS3_COL;
    localparam E_ROW  = (W_ROW - B_IN  - (3 - SS_ROW)) - SS_ROW;
    localparam E_COL  = (W_COL - W_ROW - (3 - SS_COL)) - SS_COL;
    localparam OUT_SHIFT = E_ROW + E_COL + 3 - OUT_FRAC;
    localparam WR        = W_COL + OUT_W;                       // no overflow before wrap

    // ------------------------------------------------------------- row pass
    wire                    r_valid, r_last;
    wire [2:0]              r_index;
    wire signed [W_ROW-1:0] r_data;
    dct8_core #(.B_IN(B_IN), .W(W_ROW), .G(G_ROW), .SS1(SS1_ROW), .SS2(SS2_ROW), .SS3(SS3_ROW),
                .MR_MODE(MR_MODE), .STYLE(STYLE)) u_row (
        .clk(clk), .rst(rst), .ce(ce), .in_valid(in_valid), .in_data(in_data),
        .out_valid(r_valid), .out_index(r_index), .out_last(r_last), .out_data(r_data));

    // ------------------------------------------------------------- transpose
    wire             t_active, t_valid;
    wire [W_ROW-1:0] t_data;
    dct8_transpose #(.W(W_ROW)) u_tr (
        .clk(clk), .rst(rst), .ce(ce), .wr_valid(r_valid), .wr_first(r_index == 3'd0),
        .wr_data(r_data), .active(t_active), .rd_valid(t_valid), .rd_data(t_data));

    // ---------------------------------------------------------- column pass
    wire                    c_valid, c_last;
    wire [2:0]              c_index;
    wire signed [W_COL-1:0] c_data;
    dct8_core #(.B_IN(W_ROW), .W(W_COL), .G(G_COL), .SS1(SS1_COL), .SS2(SS2_COL), .SS3(SS3_COL),
                .MR_MODE(MR_MODE), .STYLE(STYLE)) u_col (
        .clk(clk), .rst(rst), .ce(ce & t_active), .in_valid(t_valid), .in_data(t_data),
        .out_valid(c_valid), .out_index(c_index), .out_last(c_last), .out_data(c_data));

    // ------------------------------------------------------- output scaling
    wire signed [WR-1:0] c_ext = c_data;
    wire signed [WR-1:0] c_rnd;
    generate
    if (OUT_SHIFT >= 1) begin : g_rnd
        dct8_rne #(.W(WR), .S(OUT_SHIFT)) u_rnd (.z(c_ext), .q(c_rnd));
    end else begin : g_shl
        assign c_rnd = c_ext <<< (-OUT_SHIFT);
    end
    endgenerate

    reg [2:0] v_cnt;
    always @(posedge clk) begin
        if (rst) begin
            out_valid <= 1'b0;
            out_u     <= 3'd0;
            out_v     <= 3'd0;
            out_data  <= {OUT_W{1'b0}};
            v_cnt     <= 3'd0;
        end else if (ce) begin
            out_valid <= c_valid;
            out_u     <= c_index;
            out_v     <= v_cnt;
            out_data  <= c_rnd[OUT_W-1:0];
            if (c_valid && c_last)
                v_cnt <= v_cnt + 3'd1;
        end
    end
endmodule
