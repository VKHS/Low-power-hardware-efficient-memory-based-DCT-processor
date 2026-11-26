function q = dct8_rno(z, s)
%DCT8_RNO  Round-half-to-odd arithmetic right shift by s bits (element-wise).
%   For s = 1 this is von Neumann rounding ("jamming") of the SS units:
%   (z >>> 1) | z[0] -- unbiased, no adder, and it never rounds 2^(W-1) - 1/2
%   up to 2^(W-1), so a safe-scaling stage cannot overflow.
if s == 0
    q = z;
    return;
end
q = floor(z / 2^s);
r = z - q * 2^s;
h = 2^(s - 1);
q = q + double(r > h) + double(r == h & mod(q, 2) == 0);
end
