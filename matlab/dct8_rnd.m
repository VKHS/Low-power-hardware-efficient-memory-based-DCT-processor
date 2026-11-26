function q = dct8_rnd(z, s)
%DCT8_RND  Round-half-up arithmetic right shift: floor((z + 2^(s-1)) / 2^s).
%   In hardware (z >>> s) + z[s-1].  Element-wise; exact for |z| < 2^52.
if s == 0
    q = z;
else
    q = floor((z + 2^(s - 1)) / 2^s);
end
end
