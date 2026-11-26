function demo_dct8(img)
%DEMO_DCT8  Tour of the memory-based DCT processor model.
%   DEMO_DCT8        uses a synthetic 256x256 test image
%   DEMO_DCT8(IMG)   uses IMG (grayscale uint8 / double 0..255, or a file name)
%   Prints the micro-rotation table of both CORDIC modes, the accuracy versus
%   word length (WL) of the 1-D processor, and the PSNR of zonal compression
%   (64:10, 64:6, 64:3, 64:1 as in the paper) through the bit-accurate 2-D model;
%   shows the reconstructed images when a display is available.
if nargin < 1
    img = synthetic_image(256);
elseif ischar(img)
    img = imread(img);
end
img = double(img);
if size(img, 3) == 3
    img = round(0.299 * img(:, :, 1) + 0.587 * img(:, :, 2) + 0.114 * img(:, :, 3));
end
img = img(1:8 * floor(end / 8), 1:8 * floor(size(img, 2) / 8));

% ---------------------------------------------------------------- micro-rotations
fprintf('\nCentral CORDIC unit: realised angles (target k*pi/16)\n');
modes = {'table1', 'cordic2x'};
for m = 1:2
    for k = 1:3
        [u, v] = dct8_cordic(2^20, 0, k, 0, modes{m});
        fprintf('  %-8s k=%d  target %7.4f deg  realised %8.5f deg  error %+.2e rad  gain %.6f\n', ...
            modes{m}, k, k * 180 / 16, atan2(v, u) * 180 / pi, atan2(v, u) - k * pi / 16, ...
            hypot(u, v) / 2^20);
    end
end

% ---------------------------------------------------------------- accuracy vs WL
rng(1);
x = floor(rand(5000, 8) * 256) - 128;
Xref = x * dct8_ref().';
fprintf('\n1-D processor: SQNR (dB) versus word length (best safe-scaling choice)\n');
fprintf('   WL   table1  cordic2x\n');
for w = 8:16
    s = zeros(1, 2);
    for m = 1:2
        best = -inf;
        for code = 0:7
            ss = bitget(code, 3:-1:1);
            if w - 8 - (3 - sum(ss)) < 0, continue; end
            cfg = dct8_cfg(8, w, 3, ss, modes{m});
            Y = dct8_fixed(x, cfg) / (2 * sqrt(2) * 2^cfg.E);
            best = max(best, 10 * log10(sum(Xref(:).^2) / sum((Y(:) - Xref(:)).^2)));
        end
        s(m) = best;
    end
    fprintf('  %3d   %6.2f   %6.2f\n', w, s(1), s(2));
end

% ---------------------------------------------------------------- image, zonal coding
row = dct8_cfg(8, 14, 3, [0 0 0], 'table1');
col = dct8_cfg(14, 16, 3, [1 1 1], 'table1');
[h, wd] = size(img);
B = permute(reshape(img - 128, 8, h / 8, 8, wd / 8), [1 3 2 4]);
B = reshape(B, 8, 8, []);
C = dct2d_fixed(B, row, col, 16, 2) / 4;          % two fractional bits
zz = zigzag8();
keeps = [10 6 3 1];
rec = cell(1, numel(keeps));
c8 = dct8_ref();
fprintf('\nZonal compression through the bit-accurate 2-D processor (WL 14/16, Table 1)\n');
for i = 1:numel(keeps)
    mask = zeros(8);
    mask(zz(1:keeps(i))) = 1;
    R = zeros(size(C));
    for n = 1:size(C, 3)
        R(:, :, n) = c8.' * (C(:, :, n) .* mask) * c8;
    end
    R = reshape(permute(reshape(R, 8, 8, h / 8, wd / 8), [1 3 2 4]), h, wd) + 128;
    rec{i} = min(max(round(R), 0), 255);
    mse = mean((rec{i}(:) - img(:)).^2);
    fprintf('  64:%-2d  PSNR %6.2f dB\n', keeps(i), 10 * log10(255^2 / mse));
end
if usejava('desktop') || ~isempty(getenv('DISPLAY'))
    figure('Name', 'memory-based DCT processor: zonal compression');
    for i = 1:numel(keeps)
        subplot(2, 2, i);
        imagesc(rec{i}, [0 255]); colormap(gray); axis image off;
        title(sprintf('64:%d', keeps(i)));
    end
end
end

function idx = zigzag8()
% linear indices (column-major, 8x8) of the JPEG zig-zag scan
idx = zeros(1, 64);
n = 0;
for s = 0:14
    if mod(s, 2) == 0
        rr = min(s, 7):-1:max(0, s - 7);
    else
        rr = max(0, s - 7):min(s, 7);
    end
    for r = rr
        c = s - r;
        n = n + 1;
        idx(n) = r + 1 + 8 * c;
    end
end
end

function img = synthetic_image(n)
% smooth gradients, sharp edges, a disc and fine texture
[xx, yy] = meshgrid(0:n - 1, 0:n - 1);
img = 96 + 64 * sin(2 * pi * xx / n) .* cos(2 * pi * yy / (2 * n));
img(hypot(xx - n / 2, yy - n / 2) < n / 5) = 220;
img(yy > 3 * n / 4) = 40 + 30 * mod(floor(xx(yy > 3 * n / 4) / 2), 2);
img(:, 1:n / 8) = 30;
img = min(max(round(img), 0), 255);
end
