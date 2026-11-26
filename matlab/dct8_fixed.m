function Y = dct8_fixed(X, cfg)
%DCT8_FIXED  Bit-accurate model of the memory-based radix-2 8-point DCT processor.
%   Y = DCT8_FIXED(X, CFG) transforms every row of the N-by-8 integer matrix X
%   (B_IN-bit inputs) and returns the N-by-8 W-bit output words Y_0..Y_7 with
%   Y_k = 2*sqrt(2) * X_k * 2^CFG.E (X_k: orthonormal DCT-II), exactly as the
%   RTL produces them.  CFG comes from DCT8_CFG.
%
%   Flow graph (scalable radix-2 DCT, three butterfly and two rotation levels):
%     stage 1  S: (x[2n], x[2n+1])       -> x_L, x_H
%     stage 2  T: 4-point sub-DCT inputs
%     stage 3  U: 2-point DCTs, V: rotations by -pi/8
%     stage 4  W: rotations by -pi/16, -2pi/16, -3pi/16
%   A rotation by -theta is a counter-clockwise rotation of swapped operands.
X = double(X);
if size(X, 2) ~= 8
    error('dct8_fixed:size', 'X must have 8 columns');
end
lo = -2^(cfg.b_in - 1);
hi = 2^(cfg.b_in - 1) - 1;
if any(X(:) < lo | X(:) > hi | X(:) ~= round(X(:)))
    error('dct8_fixed:range', 'inputs must be %d-bit integers', cfg.b_in);
end
x = X * 2^cfg.F;                                   % input alignment
w = cfg.w;
[L0, H0] = bf(x(:, 1), x(:, 2), cfg.ss(1), w);     % S0..S3
[L1, H1] = bf(x(:, 3), x(:, 4), cfg.ss(1), w);
[L2, H2] = bf(x(:, 5), x(:, 6), cfg.ss(1), w);
[L3, H3] = bf(x(:, 7), x(:, 8), cfg.ss(1), w);
[LL0, LH0] = bf(L0, L1, cfg.ss(2), w);             % T0..T3
[LL1, LH1] = bf(L2, L3, cfg.ss(2), w);
[HH0, HL0] = bf(H0, H1, cfg.ss(2), w);
[HH1, HL1] = bf(H2, H3, cfg.ss(2), w);
[Y0, D] = bf(LL0, LL1, cfg.ss(3), w);              % U0..U3
[Sp, Dp] = bf(LH0, LH1, cfg.ss(3), w);
[Y4, DB] = bf(HL0, HL1, cfg.ss(3), w);
[SBp, DBp] = bf(HH0, HH1, cfg.ss(3), w);
[A3, A1] = mr(Sp, D, 2, cfg);                      % V0, V1: -pi/8
[B3, B1] = mr(SBp, DB, 2, cfg);
[Y7, Y1] = mr(B3, A1, 1, cfg);                     % W1: -pi/16
[Y6, Y2] = mr(DBp, Dp, 2, cfg);                    % W2: -2pi/16
[Y5, Y3] = mr(B1, A3, 3, cfg);                     % W3: -3pi/16
Y = [Y0, Y1, Y2, Y3, Y4, Y5, Y6, Y7];
end

function [s, d] = bf(p, q, scale, w)
% butterfly datapath with its SS unit (x 1/2, von Neumann rounding)
if scale
    s = dct8_wrap(dct8_rno(p + q, 1), w);
    d = dct8_wrap(dct8_rno(p - q, 1), w);
else
    s = dct8_wrap(p + q, w);
    d = dct8_wrap(p - q, w);
end
end

function [u, v] = mr(p, q, k, cfg)
[u, v] = dct8_cordic(p, q, k, cfg.g, cfg.mode);
u = dct8_wrap(u, cfg.w);
v = dct8_wrap(v, cfg.w);
end
