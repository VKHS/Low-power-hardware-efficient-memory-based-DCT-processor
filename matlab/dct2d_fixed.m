function C = dct2d_fixed(B, row, col, out_w, out_frac)
%DCT2D_FIXED  Bit-accurate 8x8 2-D DCT of the two-pass processor (rtl/dct2d_8x8.v).
%   C = DCT2D_FIXED(B, ROW, COL, OUT_W, OUT_FRAC)
%     B       8-by-8-by-N integer blocks, B(r, c, n) = pixel (row r, column c)
%     ROW     DCT8_CFG of the row pass (input B_IN bits)
%     COL     DCT8_CFG of the column pass (input = row word length)
%     OUT_W   output word length, OUT_FRAC fractional output bits
%   Returns C(u, v, n) = X[u][v] * 2^OUT_FRAC as OUT_W-bit integers.
%   The two post-scaling factors 2*sqrt(2) combine to 8, so the column output
%   is 2^(E_row + E_col + 3) X and the final stage only shifts (round half to
%   even, or an exact left shift for very short word lengths).
if nargin < 4, out_w = 12; end
if nargin < 5, out_frac = 0; end
if col.b_in ~= row.w
    error('dct2d_fixed:width', 'column input width must equal the row word length');
end
n = size(B, 3);
R = reshape(permute(double(B), [2 1 3]), 8, 8 * n).';       % (r, n) x c
Yr = dct8_fixed(R, row);                                    % (r, n) x v
Ci = reshape(permute(reshape(Yr, 8, n, 8), [3 2 1]), 8 * n, 8);   % (v, n) x r
Yc = dct8_fixed(Ci, col);                                   % (v, n) x u
C = permute(reshape(Yc, 8, n, 8), [3 1 2]);                 % u x v x n
s = row.E + col.E + 3 - out_frac;
if s >= 1
    C = dct8_rne(C, s);
else
    C = C * 2^(-s);
end
C = dct8_wrap(C, out_w);
end
