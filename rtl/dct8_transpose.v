// ============================================================================
// dct8_transpose.v -- single-buffer 8x8 transpose memory
// ----------------------------------------------------------------------------
// 64 words.  In every cycle one location is READ (previous block, transposed
// order) and immediately RE-WRITTEN with the incoming word (current block).
// Consecutive blocks therefore alternate between row-major and column-major
// addressing:
//      mode 0 : addr = tau                       (row-major)
//      mode 1 : addr = 8*(tau mod 8) + tau div 8  (column-major) = {tau[2:0], tau[5:3]}
// so one 64-word memory replaces the usual 2 x 64-word ping-pong buffer.
// The frame counter starts with the first coefficient of the first valid block;
// a frame's valid tag is the write-side valid seen at tau = 0.
// ============================================================================

module dct8_transpose #(
    parameter W = 12
) (
    input  wire         clk,
    input  wire         rst,
    input  wire         ce,
    input  wire         wr_valid,     // row-processor out_valid
    input  wire         wr_first,     // row-processor out_index == 0
    input  wire [W-1:0] wr_data,
    output wire         active,       // frame counter running (enables column core)
    output wire         rd_valid,     // tag of the frame being read
    output wire [W-1:0] rd_data
);
    reg [W-1:0] mem [0:63];
    reg [5:0]   tau;
    reg         mode, started, frame_tag, read_tag;

    wire       start_now = ~started & wr_valid & wr_first;
    assign     active    = started | start_now;
    wire [5:0] addr      = mode ? {tau[2:0], tau[5:3]} : tau;
    assign     rd_data   = mem[addr];
    assign     rd_valid  = read_tag;

    always @(posedge clk) begin
        if (rst) begin
            tau       <= 6'd0;
            mode      <= 1'b0;
            started   <= 1'b0;
            frame_tag <= 1'b0;
            read_tag  <= 1'b0;
        end else if (ce && active) begin
            mem[addr] <= wr_data;
            started   <= 1'b1;
            tau       <= tau + 6'd1;
            if (tau == 6'd0)
                frame_tag <= wr_valid;
            if (tau == 6'd63) begin
                mode     <= ~mode;
                read_tag <= frame_tag;
            end
        end
    end
endmodule
