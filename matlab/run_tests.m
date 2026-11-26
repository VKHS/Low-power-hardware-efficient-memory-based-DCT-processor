function run_tests()
%RUN_TESTS  Self-checking test of the MATLAB/Octave model.
%   1. bit-exact against every vector set in ../vectors (the same vectors the
%      RTL and HLS test benches use): 1-D and 2-D processors, all configurations
%   2. accuracy of both micro-rotation modes against the double-precision DCT
%   3. vectorised 2-D model == block-by-block model
%   4. 16-point extension against the 16-point DCT
%   Ends with error() if anything fails (non-zero exit status in batch mode):
%       octave --no-gui --eval "addpath('matlab'); run_tests"
%       matlab -batch "addpath('matlab'); run_tests"
here = fileparts(mfilename('fullpath'));
vec = fullfile(here, '..', 'vectors');
man = jsondecode(fileread(fullfile(vec, 'manifest.json')));
names = fieldnames(man);
nfail = 0;

% ------------------------------------------------------------- 1. golden vectors
for i = 1:numel(names)
    nm = names{i};
    e = man.(nm);
    p = e.params;
    X = load(fullfile(vec, [nm '_in.txt']));
    Yexp = load(fullfile(vec, [nm '_out.txt']));
    if strcmp(e.kind, 'dct8')
        cfg = dct8_cfg(p.B_IN, p.W, p.G, [p.SS1 p.SS2 p.SS3], e.mr_mode);
        Y = dct8_fixed(X, cfg);
    else
        row = dct8_cfg(p.B_IN, p.W_ROW, p.G_ROW, [p.SS1_ROW p.SS2_ROW p.SS3_ROW], e.mr_mode);
        col = dct8_cfg(p.W_ROW, p.W_COL, p.G_COL, [p.SS1_COL p.SS2_COL p.SS3_COL], e.mr_mode);
        nb = size(X, 1);
        B = permute(reshape(X.', 8, 8, nb), [2 1 3]);          % B(r, c, n)
        C = dct2d_fixed(B, row, col, p.OUT_W, p.OUT_FRAC);
        Y = reshape(permute(C, [2 1 3]), 64, nb).';             % row-major lines
    end
    nfail = nfail + report(sprintf('%-14s bit-exact (%d words)', nm, numel(Yexp)), ...
                           isequal(Y, Yexp));
end

% ------------------------------------------------------------- 2. accuracy
rng(2022);
x = floor(rand(4000, 8) * 256) - 128;
Xref = x * dct8_ref().';
cases = {8, 14, 3, [0 0 0], 'table1',   0.40; ...
         8, 14, 3, [0 0 0], 'cordic2x', 0.03; ...
         8, 10, 3, [1 1 1], 'table1',   0.60; ...
         8,  8, 3, [1 1 1], 'cordic2x', 2.00};
for i = 1:size(cases, 1)
    cfg = dct8_cfg(cases{i, 1}, cases{i, 2}, cases{i, 3}, cases{i, 4}, cases{i, 5});
    Yr = dct8_fixed(x, cfg) / (2 * sqrt(2) * 2^cfg.E);
    rms = sqrt(mean((Yr(:) - Xref(:)).^2));
    nfail = nfail + report(sprintf('accuracy W=%-2d SS=%d%d%d %-8s rms %.4f < %.2f', ...
        cfg.w, cfg.ss, cfg.mode, rms, cases{i, 6}), rms < cases{i, 6});
end
% full-scale DC is exact and never overflows
cfg = dct8_cfg(8, 8, 3, [1 1 1], 'table1');
y = dct8_fixed(-128 * ones(1, 8), cfg);
nfail = nfail + report('full-scale DC = -2^(W-1), AC = 0', isequal(y, [-128 0 0 0 0 0 0 0]));

% ------------------------------------------------------------- 3. 2-D: vectorised == per block
row = dct8_cfg(8, 14, 3, [0 0 0], 'cordic2x');
col = dct8_cfg(14, 16, 3, [1 1 1], 'cordic2x');
B = floor(rand(8, 8, 20) * 256) - 128;
C = dct2d_fixed(B, row, col, 14, 2);
ok = true;
for n = 1:size(B, 3)
    Yr = dct8_fixed(B(:, :, n), row);          % rows: [r][v]
    Yc = dct8_fixed(Yr.', col).';              % [u][v]
    ref = dct8_wrap(dct8_rne(Yc, row.E + col.E + 3 - 2), 14);
    ok = ok && isequal(C(:, :, n), ref);
end
nfail = nfail + report('2-D vectorised model == block-by-block model', ok);
c8 = dct8_ref();
err = 0;
for n = 1:size(B, 3)
    err = max(err, max(max(abs(C(:, :, n) / 4 - c8 * B(:, :, n) * c8.'))));
end
nfail = nfail + report(sprintf('2-D accuracy (cordic2x, 2 fractional bits): max error %.3f', err), err < 0.6);

% ------------------------------------------------------------- 4. 16-point extension
x16 = floor(rand(2000, 16) * 256) - 128;
cfg8 = dct8_cfg(9, 15, 3, [0 0 0], 'cordic2x');
Z = dct16_fixed(x16, cfg8, 3) / (4 * 2^cfg8.E);
Zref = x16 * dct8_ref(16).';
rms = sqrt(mean((Z(:) - Zref(:)).^2));
nfail = nfail + report(sprintf('16-point (two 8-point engines + Table 5 CORDIC array) rms %.3f', rms), rms < 0.3);

if nfail > 0
    error('run_tests:fail', '%d test(s) failed', nfail);
end
fprintf('ALL PASS\n');
end

function f = report(msg, ok)
if ok
    fprintf('PASS  %s\n', msg);
    f = 0;
else
    fprintf('FAIL  %s\n', msg);
    f = 1;
end
end
