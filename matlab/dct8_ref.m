function C = dct8_ref(n)
%DCT8_REF  Orthonormal N-point DCT-II matrix (default N = 8): X = C * x.
if nargin < 1, n = 8; end
[m, k] = meshgrid(0:n - 1, 0:n - 1);
C = sqrt(2 / n) * cos((2 * m + 1) .* k * pi / (2 * n));
C(1, :) = C(1, :) / sqrt(2);
end
