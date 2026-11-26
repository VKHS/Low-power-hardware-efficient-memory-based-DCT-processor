function Z = dct16_fixed(X, cfg8, g)
%DCT16_FIXED  16-point DCT from two 8-point processors and a CORDIC array.
%   Z = DCT16_FIXED(X, CFG8, G): X is N-by-16 with (CFG8.b_in - 1)-bit inputs,
%   CFG8 the configuration of both 8-point engines (input = stage-1 outputs),
%   G the guard bits of the CORDIC array.  Returns Z = 4 * X16 * 2^CFG8.E.
%
%   x_L = x[2m] + x[2m+1], x_H = x[2m] - x[2m+1];  A = DCT8(x_L), B = DCT8((-1)^m x_H)
%   Z[0] = A[0], Z[8] = B[0], (Z[k], Z[16-k]) = Rot(-k pi/32)(A[k], B[8-k]), k = 1..7
%   with the Gaussian integers of the paper's Table 5:
%   10+j, 10+j2, 10+j3, 50+j21, 50+j27, 50+j33, 50+j41.
if nargin < 3, g = 3; end
X = double(X);
xl = X(:, 1:2:end) + X(:, 2:2:end);
sg = repmat([1 -1], 1, 4);
xh = (X(:, 1:2:end) - X(:, 2:2:end)) .* repmat(sg, size(X, 1), 1);
A = dct8_fixed(xl, cfg8);
B = dct8_fixed(xh, cfg8);
P = [10 1; 10 2; 10 3; 50 21; 50 27; 50 33; 50 41];
Z = zeros(size(X, 1), 16);
Z(:, 1) = A(:, 1);
Z(:, 9) = B(:, 1);
for k = 1:7
    T = csd_greedy(1 / hypot(P(k, 1), P(k, 2)), 4);
    u = B(:, 8 - k + 1) * 2^g;       % CCW rotation of the swapped pair (B[8-k], A[k])
    v = A(:, k + 1) * 2^g;
    xa = P(k, 1) * u - P(k, 2) * v;
    ya = P(k, 2) * u + P(k, 1) * v;
    hi = dct8_rne(csd(xa, T), g);
    lo = dct8_rne(csd(ya, T), g);
    Z(:, k + 1) = dct8_wrap(lo, cfg8.w);
    Z(:, 16 - k + 1) = dct8_wrap(hi, cfg8.w);
end
end

function T = csd_greedy(value, nterms)
% value ~ sum(sign * 2^-shift), rows [shift sign]
T = zeros(0, 2);
r = value;
for i = 1:nterms
    if r == 0, break; end
    e = round(log2(abs(r)));
    T(end + 1, :) = [-e, sign(r)]; %#ok<AGROW>
    r = r - sign(r) * 2^e;
end
end

function acc = csd(x, T)
acc = zeros(size(x));
for i = 1:size(T, 1)
    acc = acc + T(i, 2) * dct8_rnd(x, T(i, 1));
end
end
