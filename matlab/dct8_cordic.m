function [xo, yo] = dct8_cordic(u, v, k, g, mode)
%DCT8_CORDIC  Central CORDIC unit: counter-clockwise rotation by ~k*pi/16, k = 1..3.
%   [XO, YO] = DCT8_CORDIC(U, V, K, G, MODE), bit-accurate (element-wise on
%   integer-valued arrays), identical to rtl/cordic2_mr.v and
%   python/dct8/cordic2.py.  The outputs are NOT yet wrapped to W bits.
%
%   MODE 'table1'   : radius scale-up (G guard bits) -> exact rotation by the
%                     Gaussian integer P_k of the paper's Table 1
%                     (10+j2, 50+j21, 50+j33) -> radius scale-down
%                     K_k ~ 1/|P_k| (four signed powers of two) -> rounding.
%   MODE 'cordic2x' : friend angle (7+j)/8 | (5+5j)/8 -> USR 2^-3 -> USR 2^-5
%                     -> nano-rotation -> one radius scaling
%                     K = 1 + 2^-3 - 2^-6 + 2^-8 - 2^-11 -> rounding.
x0 = u * 2^g;
y0 = v * 2^g;
if strcmp(mode, 'table1')
    P = [10 2; 50 21; 50 33];
    a = P(k, 1);
    b = P(k, 2);
    xa = a * x0 - b * y0;
    ya = b * x0 + a * y0;
    T = table1_k(k);
    xo = dct8_rne(csd(xa, T), g);
    yo = dct8_rne(csd(ya, T), g);
else
    C = [0  0 1 -1  0;          % k -> [f s3 s5 n7 n9]
         0  1 0  0  1;
         1 -1 1 -1 -1];
    f = C(k, 1); s3 = C(k, 2); s5 = C(k, 3); n7 = C(k, 4); n9 = C(k, 5);
    if f
        x1 = dct8_rnd(5 * (x0 - y0), 3);
        y1 = dct8_rnd(5 * (x0 + y0), 3);
    else
        x1 = dct8_rnd(7 * x0 - y0, 3);
        y1 = dct8_rnd(x0 + 7 * y0, 3);
    end
    [x2, y2] = usr(x1, y1, s3, 3);
    [x3, y3] = usr(x2, y2, s5, 5);
    x4 = x3 - n7 * dct8_rnd(y3, 7) - n9 * dct8_rnd(y3, 9);
    y4 = y3 + n7 * dct8_rnd(x3, 7) + n9 * dct8_rnd(x3, 9);
    RS = [0 1; 3 1; 6 -1; 8 1; 11 -1];
    xo = dct8_rne(csd(x4, RS), g);
    yo = dct8_rne(csd(y4, RS), g);
end
end

function T = table1_k(k)
% radius scale-down K_k as rows [shift sign]
if k == 1
    T = [3 1; 5 -1; 8 1; 11 1];
elseif k == 2
    T = [6 1; 8 1; 10 -1; 13 -1];
else
    T = [6 1; 10 1; 13 1; 15 -1];
end
end

function acc = csd(x, T)
acc = zeros(size(x));
for i = 1:size(T, 1)
    acc = acc + T(i, 2) * dct8_rnd(x, T(i, 1));
end
end

function [xo, yo] = usr(x, y, s, k)
% uniformly-scaled redundant CORDIC stage, rotation s * 2*atan(2^-k)
if s ~= 0
    xo = x - dct8_rnd(x, 2 * k) - s * dct8_rnd(y, k - 1);
    yo = y - dct8_rnd(y, 2 * k) + s * dct8_rnd(x, k - 1);
else
    xo = x + dct8_rnd(x, 2 * k);
    yo = y + dct8_rnd(y, 2 * k);
end
end
