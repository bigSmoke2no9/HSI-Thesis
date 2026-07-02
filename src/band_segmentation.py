"""Automatic spectral band segmentation from datacube correlation."""

import numpy as np


def get_band_regions(X, min_bands=20, max_segments=6):
    """
    Split an HSI cube into contiguous spectral regions.

    Segment count and boundaries are inferred from the band-band
    correlation matrix (no manual n_segments).

    Parameters
    ----------
    X : ndarray, shape (H, W, B)
        Hyperspectral datacube.
    min_bands : int
        Minimum bands per region.
    max_segments : int
        Upper limit when searching for the best segment count.

    Returns
    -------
    list of ndarray
        3D sub-cubes, one per region.
    """
    if X.ndim != 3:
        raise ValueError("X must have shape (H, W, B)")

    n_bands = X.shape[2]
    if n_bands < 2 * min_bands:
        return [X]
    pixels = X.reshape(-1, X.shape[2]).astype(np.float64)
    corr = np.corrcoef(pixels.T)
    n_segments, breaks = _auto_segment(corr, min_bands, max_segments)
    bounds = [0] + breaks + [n_bands]
    return [X[:, :, bounds[i] : bounds[i + 1]] for i in range(n_segments)]
 


def _within_corr(corr, start, end):
    size = end - start
    if size < 2:
        return 0.0
    block = np.abs(corr[start:end, start:end])
    return block[np.triu_indices(size, k=1)].mean()


def _cross_corr(corr, split):
    if split <= 0 or split >= corr.shape[0]:
        return 0.0
    return np.abs(corr[:split, split:]).mean()


def _dp_partition(corr, max_segments, min_bands):
    """
    One DP pass: best score to partition [0, i) into k segments.
    Returns (scores_at_B, parents) for backtracking.
    """
    n_bands = corr.shape[0]
    neg = -np.inf

    best = [[neg] * (n_bands + 1) for _ in range(max_segments + 1)]
    parent = [[None] * (n_bands + 1) for _ in range(max_segments + 1)]
    best[0][0] = 0.0

    for k in range(1, max_segments + 1):
        for end in range(k * min_bands, n_bands + 1):
            for start in range((k - 1) * min_bands, end - min_bands + 1):
                if best[k - 1][start] == neg:
                    continue
                score = (
                    best[k - 1][start]
                    + _within_corr(corr, start, end)
                    - (_cross_corr(corr, end) if end < n_bands else 0.0)
                )
                if score > best[k][end]:
                    best[k][end] = score
                    parent[k][end] = start

    scores = {
        k: best[k][n_bands]
        for k in range(1, max_segments + 1)
        if best[k][n_bands] > neg
    }
    return scores, parent


def _backtrack_breaks(parent, n_segments, n_bands):
    breaks = []
    end = n_bands
    for k in range(n_segments, 1, -1):
        start = parent[k][end]
        if start is None:
            raise RuntimeError("Could not find valid segmentation.")
        breaks.append(start)
        end = start
    breaks.reverse()
    return breaks


def _auto_n_segments(scores):
    """
    Pick segment count from DP scores using the largest marginal gain.

    scores : dict {k: objective} for k = 1, 2, ...
    """
    ks = sorted(scores)
    if len(ks) == 1:
        return ks[0]

    best_k, best_gain = ks[0], -np.inf
    for i in range(1, len(ks)):
        gain = scores[ks[i]] - scores[ks[i - 1]]
        if gain > best_gain:
            best_gain = gain
            best_k = ks[i]
    return max(2, best_k)


def _auto_segment(corr, min_bands, max_segments):
    n_bands = corr.shape[0]
    max_k = min(max_segments, n_bands // min_bands)
    max_k = max(2, max_k)

    scores, parent = _dp_partition(corr, max_k, min_bands)
    if 1 not in scores:
        scores[1] = _within_corr(corr, 0, n_bands)

    n_segments = _auto_n_segments(scores)
    breaks = _backtrack_breaks(parent, n_segments, n_bands)
    return n_segments, breaks
