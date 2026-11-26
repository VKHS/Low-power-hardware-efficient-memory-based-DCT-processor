// ============================================================================
// dct8_mem_bank.v -- multi-port register-file memory bank
// ----------------------------------------------------------------------------
// N words of W bits, NWP write ports, NRP asynchronous read ports.
// Reads return the value stored before the clock edge (read-before-write), so
// a word may be read and overwritten in the same cycle.  The modulo schedule
// guarantees that no two write ports address the same word in one cycle.
// Used three times in dct8_core (sizes and ports from the modulo schedule):
//   BM  butterfly buffers M_B   8 words  4 W / 4 R   (read by the butterfly unit)
//   MM  memory bank             5 words  6 W / 2 R   (read by the CORDIC unit)
//   OB  output buffer           5 words  6 W / 1 R   (rearrange unit)
// Only the write ports the schedule actually uses are ever enabled.
// ============================================================================

module dct8_mem_bank #(
    parameter N   = 8,
    parameter AW  = 3,
    parameter W   = 12,
    parameter NWP = 1,
    parameter NRP = 1
) (
    input  wire               clk,
    input  wire               ce,
    input  wire [NWP-1:0]     we,
    input  wire [NWP*AW-1:0]  waddr,
    input  wire [NWP*W-1:0]   wdata,
    input  wire [NRP*AW-1:0]  raddr,
    output wire [NRP*W-1:0]   rdata
);
    reg [W-1:0] mem [0:N-1];

    integer p;
    always @(posedge clk) begin
        if (ce) begin
            for (p = 0; p < NWP; p = p + 1) begin
                if (we[p])
                    mem[waddr[p*AW +: AW]] <= wdata[p*W +: W];
            end
        end
    end

    genvar r;
    generate
        for (r = 0; r < NRP; r = r + 1) begin : g_rd
            assign rdata[r*W +: W] = mem[raddr[r*AW +: AW]];
        end
    endgenerate
endmodule
