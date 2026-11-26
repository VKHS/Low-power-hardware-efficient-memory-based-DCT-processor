"""Floating-point references: orthonormal DCT-II / DCT-III (IDCT), 1-D and 2-D."""
from __future__ import annotations

import numpy as np

N = 8


def dct_matrix(n: int = N) -> np.ndarray:
    """Orthonormal DCT-II matrix ``C`` with ``X = C @ x``."""
    k = np.arange(n)[:, None]
    m = np.arange(n)[None, :]
    c = np.sqrt(2.0 / n) * np.cos((2 * m + 1) * k * np.pi / (2 * n))
    c[0, :] /= np.sqrt(2.0)
    return c


C8 = dct_matrix(N)


def dct8(x) -> np.ndarray:
    """Orthonormal 8-point DCT-II along the last axis."""
    return np.asarray(x, dtype=float) @ C8.T


def idct8(X) -> np.ndarray:
    """Inverse of :func:`dct8` (orthonormal DCT-III) along the last axis."""
    return np.asarray(X, dtype=float) @ C8


def dct2(block) -> np.ndarray:
    """Orthonormal 8x8 2-D DCT-II, ``X[u, v]`` (u: vertical, v: horizontal frequency)."""
    b = np.asarray(block, dtype=float)
    return C8 @ b @ C8.T


def idct2(coef) -> np.ndarray:
    """Inverse of :func:`dct2`."""
    c = np.asarray(coef, dtype=float)
    return C8.T @ c @ C8


def blockwise(img: np.ndarray, fn, n: int = N) -> np.ndarray:
    """Apply ``fn`` to every non-overlapping ``n x n`` block of ``img``."""
    h, w = img.shape
    out = np.empty((h, w), dtype=float)
    for r in range(0, h, n):
        for c in range(0, w, n):
            out[r:r + n, c:c + n] = fn(img[r:r + n, c:c + n])
    return out
