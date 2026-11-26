function y = dct8_wrap(z, w)
%DCT8_WRAP  Two's-complement wrap-around of z to w bits (what a w-bit register does).
m = 2^w;
y = mod(z + m / 2, m) - m / 2;
end
