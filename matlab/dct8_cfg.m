function cfg = dct8_cfg(b_in, w, g, ss, mode)
%DCT8_CFG  Fixed-point configuration of the memory-based 8-point DCT processor.
%   cfg = DCT8_CFG(B_IN, W, G, SS, MODE)
%     B_IN  input word length (signed integers)                  default 8
%     W     internal word length (WL) of memory and datapaths    default 14
%     G     guard bits of the central CORDIC unit                default 3
%     SS    safe-scaling flags of butterfly stages 1..3          default [0 0 0]
%     MODE  'table1'   micro-rotations of the paper (Table 1)    default
%           'cordic2x' extended CORDIC-II configuration
%   Derived fields: H = 3 - sum(SS) headroom bits, F = W - B_IN - H input
%   fractional bits, E = F - sum(SS); every output word is
%   Y_k = 2*sqrt(2) * X_k * 2^E with X the orthonormal DCT-II.
%   Same definition as python/dct8/processor.py (Config).
if nargin < 1 || isempty(b_in), b_in = 8; end
if nargin < 2 || isempty(w), w = 14; end
if nargin < 3 || isempty(g), g = 3; end
if nargin < 4 || isempty(ss), ss = [0 0 0]; end
if nargin < 5 || isempty(mode), mode = 'table1'; end
ss = double(ss(:).');
if numel(ss) ~= 3 || any(ss ~= 0 & ss ~= 1)
    error('dct8_cfg:ss', 'SS must be three 0/1 flags');
end
if ~strcmp(mode, 'table1') && ~strcmp(mode, 'cordic2x')
    error('dct8_cfg:mode', 'MODE must be ''table1'' or ''cordic2x''');
end
cfg.b_in = b_in;
cfg.w = w;
cfg.g = g;
cfg.ss = ss;
cfg.mode = mode;
cfg.H = 3 - sum(ss);
cfg.F = w - b_in - cfg.H;
cfg.E = cfg.F - sum(ss);
if strcmp(mode, 'table1')
    cfg.wm = w + g + 8;
    max_shift = 15;
else
    cfg.wm = w + g + 1;
    max_shift = 11;
end
if g < 1
    error('dct8_cfg:g', 'G must be >= 1');
end
if cfg.F < 0
    error('dct8_cfg:w', 'W = %d too short for B_IN = %d with H = %d', w, b_in, cfg.H);
end
if cfg.wm <= max_shift
    error('dct8_cfg:wm', 'CORDIC word too short for its largest shift (use W + G >= 11)');
end
end
