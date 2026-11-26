function q = dct8_rne(z, s)
%DCT8_RNE  Round-half-to-even arithmetic right shift by s bits (element-wise).
if s == 0
    q = z;
    return;
end
q = floor(z / 2^s);
r = z - q * 2^s;
h = 2^(s - 1);
q = q + double(r > h | (r == h & mod(q, 2) == 1));
end
