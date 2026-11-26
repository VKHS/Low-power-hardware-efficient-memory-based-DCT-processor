// ============================================================================
// dct8_core.v -- low-power hardware-efficient memory-based 8-point DCT processor
// ----------------------------------------------------------------------------
// Scalable radix-2 DCT (x_L = x[2n] + x[2n+1], x_H = x[2n] - x[2n+1], applied
// recursively) on two processing elements around a partitioned memory bank:
//
//   in_data --+--> IB (1 word: x[2n] waits for x[2n+1])
//             |        |
//             +--------+--> BUTTERFLY UNIT  BF0 + BF1, each with an SS unit
//                              ^   |   (12 butterflies / block, stages 1-3)
//                              |   v
//                    BM: butterfly buffers M_B (8 words, 4R/4W)
//                                  |
//                                  v
//                    MM: memory bank (5 words, 2 read ports) <---+
//                                  |                             |
//                                  v                             |
//                    CENTRAL CORDIC UNIT (shared micro-rotations,|
//                    pi/16, pi/8, 3pi/16, 2 pipeline stages) ----+
//                                  |
//                                  v
//                    OB: output buffer = rearrange unit (5 words)
//                                  |
//                                  v  in-order Y0..Y7
//                               out_data
//
// * One sample per clock in, one coefficient per clock out, both in natural
//   order; the first coefficient of a block leaves 16 clocks after x0.
// * No multipliers.  out_data = Y_k = 2*sqrt(2) * X_k * 2^E with X_k the
//   orthonormal DCT-II and E = W - B_IN - 3 (the paper's post-scaling factor).
// * The distributed controller is four small decoders of a shared 3-bit phase
//   counter (dct8_ctrl.v, generated from the modulo schedule).  Every write
//   port and the CORDIC pipeline register are enabled only when used.
// * ce stalls the processor; in_valid is sampled with x0 and tags the block;
//   out_valid / out_index / out_last describe out_data.
// ============================================================================

module dct8_core #(
    parameter B_IN    = 8,     // input word length (signed)
    parameter W       = 14,    // internal word length (WL)
    parameter G       = 3,     // CORDIC guard bits (radius scale-up)
    parameter SS1     = 0,     // safe scaling (x 1/2) after butterfly stage 1
    parameter SS2     = 0,     //                       after butterfly stage 2
    parameter SS3     = 0,     //                       after butterfly stage 3
    parameter MR_MODE = 0,     // 0: Table 1 micro-rotations, 1: extended CORDIC-II
    parameter STYLE   = 0      // adders: 0 behavioural, 1 carry-save + CLA
) (
    input  wire                   clk,
    input  wire                   rst,        // synchronous, active high
    input  wire                   ce,
    input  wire                   in_valid,
    input  wire signed [B_IN-1:0] in_data,
    output reg                    out_valid,
    output reg  [2:0]             out_index,
    output reg                    out_last,
    output reg  signed [W-1:0]    out_data
);
`include "dct8_sched_params.vh"

    localparam H = 3 - SS1 - SS2 - SS3;      // headroom bits
    localparam F = W - B_IN - H;             // fractional bits of the input

    // ------------------------------------------------------------ phase counter
    reg [2:0] phase;
    always @(posedge clk) begin
        if (rst)
            phase <= 3'd0;
        else if (ce)
            phase <= phase + 3'd1;
    end

    // -------------------------------------------------------- input alignment
    wire signed [W-1:0] x_ext = in_data;
    wire signed [W-1:0] x_in  = x_ext <<< F;

    // ------------------------------------------------- distributed controller
    wire       b0_en, b0_a_ib, b0_b_in;
    wire [1:0] b0_stage, b0_sum_bank, b0_diff_bank;
    wire [2:0] b0_a_addr, b0_b_addr, b0_sum_addr, b0_diff_addr;
    dct8_ctrl_bf0 u_ctrl_bf0 (
        .phase(phase), .en(b0_en), .stage(b0_stage), .a_ib(b0_a_ib), .b_in(b0_b_in),
        .a_addr(b0_a_addr), .b_addr(b0_b_addr), .sum_bank(b0_sum_bank), .sum_addr(b0_sum_addr),
        .diff_bank(b0_diff_bank), .diff_addr(b0_diff_addr));

    wire       b1_en;
    wire [1:0] b1_stage, b1_sum_bank, b1_diff_bank;
    wire [2:0] b1_a_addr, b1_b_addr, b1_sum_addr, b1_diff_addr;
    dct8_ctrl_bf1 u_ctrl_bf1 (
        .phase(phase), .en(b1_en), .stage(b1_stage), .a_addr(b1_a_addr), .b_addr(b1_b_addr),
        .sum_bank(b1_sum_bank), .sum_addr(b1_sum_addr), .diff_bank(b1_diff_bank),
        .diff_addr(b1_diff_addr));

    wire       mr_issue, mr_done, mr_dst_ob;
    wire [1:0] mr_k;
    wire [2:0] mr_a_addr, mr_b_addr, mr_u_addr, mr_v_addr;
    dct8_ctrl_mr u_ctrl_mr (
        .phase(phase), .issue(mr_issue), .k(mr_k), .a_addr(mr_a_addr), .b_addr(mr_b_addr),
        .done(mr_done), .dst_ob(mr_dst_ob), .u_addr(mr_u_addr), .v_addr(mr_v_addr));

    wire       ib_we, out_start;
    wire [2:0] ob_raddr, out_k;
    dct8_ctrl_io u_ctrl_io (
        .phase(phase), .ib_we(ib_we), .ob_raddr(ob_raddr), .out_k(out_k), .out_start(out_start));

    // ------------------------------------------------- input buffer (1 word)
    reg signed [W-1:0] ib;
    always @(posedge clk) begin
        if (ce && ib_we)
            ib <= x_in;
    end

    // ------------------------------------------------------- butterfly unit
    wire signed [W-1:0] bm_rd0, bm_rd1, bm_rd2, bm_rd3;
    wire signed [W-1:0] b0_a = b0_a_ib ? ib   : bm_rd0;
    wire signed [W-1:0] b0_b = b0_b_in ? x_in : bm_rd1;
    wire signed [W-1:0] b0_sum, b0_diff, b1_sum, b1_diff;
    wire b0_scale = (b0_stage == 2'd1) ? (SS1 != 0) : (b0_stage == 2'd2) ? (SS2 != 0) : (SS3 != 0);
    wire b1_scale = (b1_stage == 2'd1) ? (SS1 != 0) : (b1_stage == 2'd2) ? (SS2 != 0) : (SS3 != 0);
    dct8_bf_pe #(.W(W)) u_bf0 (.a(b0_a),   .b(b0_b),   .scale(b0_scale), .sum(b0_sum), .diff(b0_diff));
    dct8_bf_pe #(.W(W)) u_bf1 (.a(bm_rd2), .b(bm_rd3), .scale(b1_scale), .sum(b1_sum), .diff(b1_diff));

    // -------------------------------------------------- central CORDIC unit
    wire signed [W-1:0] mm_rd0, mm_rd1, mr_u, mr_v;
    cordic2_mr #(.W(W), .G(G), .MR_MODE(MR_MODE), .STYLE(STYLE)) u_mr (
        .clk(clk), .ce(ce), .issue(mr_issue), .k(mr_k), .u(mm_rd0), .v(mm_rd1),
        .u_out(mr_u), .v_out(mr_v));

    // ----------------------------------------------------------- memory banks
    // write-port sources (fixed wiring), enabled by the decoders
    wire b0s_bm = b0_en & (b0_sum_bank  == 2'd0), b0s_mm = b0_en & (b0_sum_bank  == 2'd1);
    wire b0s_ob = b0_en & (b0_sum_bank  == 2'd2);
    wire b0d_bm = b0_en & (b0_diff_bank == 2'd0), b0d_mm = b0_en & (b0_diff_bank == 2'd1);
    wire b0d_ob = b0_en & (b0_diff_bank == 2'd2);
    wire b1s_bm = b1_en & (b1_sum_bank  == 2'd0), b1s_mm = b1_en & (b1_sum_bank  == 2'd1);
    wire b1s_ob = b1_en & (b1_sum_bank  == 2'd2);
    wire b1d_bm = b1_en & (b1_diff_bank == 2'd0), b1d_mm = b1_en & (b1_diff_bank == 2'd1);
    wire b1d_ob = b1_en & (b1_diff_bank == 2'd2);
    wire mr_mm  = mr_done & ~mr_dst_ob;
    wire mr_ob  = mr_done &  mr_dst_ob;

    // BM: butterfly buffers (read by the butterfly unit only)
    dct8_mem_bank #(.N(SCHED_BM_WORDS), .AW(3), .W(W), .NWP(4), .NRP(4)) u_bm (
        .clk(clk), .ce(ce),
        .we({b1d_bm, b1s_bm, b0d_bm, b0s_bm}),
        .waddr({b1_diff_addr, b1_sum_addr, b0_diff_addr, b0_sum_addr}),
        .wdata({b1_diff, b1_sum, b0_diff, b0_sum}),
        .raddr({b1_b_addr, b1_a_addr, b0_b_addr, b0_a_addr}),
        .rdata({bm_rd3, bm_rd2, bm_rd1, bm_rd0}));

    // MM: memory bank (operands of the central CORDIC unit, two read ports)
    dct8_mem_bank #(.N(SCHED_MM_WORDS), .AW(3), .W(W), .NWP(6), .NRP(2)) u_mm (
        .clk(clk), .ce(ce),
        .we({mr_mm, mr_mm, b1d_mm, b1s_mm, b0d_mm, b0s_mm}),
        .waddr({mr_v_addr, mr_u_addr, b1_diff_addr, b1_sum_addr, b0_diff_addr, b0_sum_addr}),
        .wdata({mr_v, mr_u, b1_diff, b1_sum, b0_diff, b0_sum}),
        .raddr({mr_b_addr, mr_a_addr}),
        .rdata({mm_rd1, mm_rd0}));

    // OB: output buffer -- the rearrange unit (in-order read-out)
    wire signed [W-1:0] ob_rd;
    dct8_mem_bank #(.N(SCHED_OB_WORDS), .AW(3), .W(W), .NWP(6), .NRP(1)) u_ob (
        .clk(clk), .ce(ce),
        .we({mr_ob, mr_ob, b1d_ob, b1s_ob, b0d_ob, b0s_ob}),
        .waddr({mr_v_addr, mr_u_addr, b1_diff_addr, b1_sum_addr, b0_diff_addr, b0_sum_addr}),
        .wdata({mr_v, mr_u, b1_diff, b1_sum, b0_diff, b0_sum}),
        .raddr(ob_raddr),
        .rdata(ob_rd));

    // -------------------------------------------- block tags and output register
    reg [SCHED_OUT_BLOCK:0] tags;     // tags[0]: block entering now, tags[i]: i blocks ago
    reg                     out_tag;
    wire                    tag_now = out_start ? tags[SCHED_OUT_BLOCK] : out_tag;
    always @(posedge clk) begin
        if (rst) begin
            tags      <= {(SCHED_OUT_BLOCK + 1){1'b0}};
            out_tag   <= 1'b0;
            out_valid <= 1'b0;
            out_index <= 3'd0;
            out_last  <= 1'b0;
            out_data  <= {W{1'b0}};
        end else if (ce) begin
            if (phase == 3'd0)
                tags <= {tags[SCHED_OUT_BLOCK-1:0], in_valid};
            if (out_start)
                out_tag <= tags[SCHED_OUT_BLOCK];
            out_valid <= tag_now;
            out_index <= out_k;
            out_last  <= (out_k == 3'd7);
            out_data  <= ob_rd;
        end
    end
endmodule
