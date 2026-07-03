"""Automatic spectral band segmentation from datacube correlation."""

import numpy as np

# Correlation tier boundaries: low | lower_mid | mid | high
_CORR_BINS = (-0.5, 0.0, 0.5)


def _compute_corr(X):
    """Band-band Pearson correlation matrix, shape (B, B)."""
    pixels = X.reshape(-1, X.shape[2]).astype(np.float64)
    return np.corrcoef(pixels.T)


def _band_corr_scores(corr):
    """Mean signed correlation of each band with all other bands."""
    n_bands = corr.shape[0]
    mask = ~np.eye(n_bands, dtype=bool)
    return (corr * mask).sum(axis=1) / (n_bands - 1)


def get_band_corr_groups(X):
    """
    Group band indices into four correlation tiers from the datacube.

    Uses the 2D correlation matrix ``corr = np.corrcoef(pixels.T)``.
    Each band gets a score = mean signed corr with all other bands.
    Bands are assigned to fixed tiers (lower corr -> lower row index):

    ======  ====================  ================
    row     tier                  corr range
    ======  ====================  ================
    0       low                   [-1.0, -0.5)
    1       lower_mid             [-0.5,  0.0)
    2       mid                   [ 0.0,  0.5)
    3       high                  [ 0.5,  1.0]
    ======  ====================  ================

    Parameters
    ----------
    X : ndarray, shape (H, W, B)
        Hyperspectral datacube.

    Returns
    -------
    ndarray, shape (4,), dtype object
        Each element is a 1D ``int`` array of 0-based band indices for that
        tier (sorted ascending). Tiers with no bands are empty arrays.
    """
    if X.ndim != 3:
        raise ValueError("X must have shape (H, W, B)")

    corr = _compute_corr(X)
    scores = _band_corr_scores(corr)
    tiers = np.digitize(scores, bins=_CORR_BINS)

    groups = [[] for _ in range(4)]
    for band_idx, tier in enumerate(tiers):
        groups[int(tier)].append(int(band_idx))

    return np.array(
        [np.asarray(sorted(idxs), dtype=np.int32) for idxs in groups],
        dtype=object,
    )


def get_band_regions(X, threshold=0.5, window_size=None, min_bands=30):
    """
    Split an HSI cube into contiguous spectral regions.

    Algorithm
    ---------
    1. corr = np.corrcoef(pixels.T)
    2. For each band, build a window corrcoef sum via 1D convolution.
    3. diff[i] = |profile[i + 1] - profile[i]|  (jump to next window)
    4. score = max(diff) * threshold
    5. New segment when diff[i] > score, else keep the same segment.

    Parameters
    ----------
    X : ndarray, shape (H, W, B)
        Hyperspectral datacube.
    threshold : float
        Fraction of the largest window jump used as the split score.
    window_size : int or None
        Convolution window length. Defaults to max(5, B // 20).
    min_bands : int
        Minimum bands per region; shorter segments are merged.

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

    corr = _compute_corr(X)
    breaks = _corr_diff_breaks(corr, threshold, window_size, min_bands)

    bounds = [0] + breaks + [n_bands]
    return [X[:, :, bounds[i] : bounds[i + 1]] for i in range(len(bounds) - 1)]


def _window_profile(corr, window_size):
    """
    Convolution sum of adjacent-band |corr| at each spectral position.

    links[i] = |corr(i, i + 1)|
    profile  = convolve(links, ones(window_size))
    """
    n_bands = corr.shape[0]
    win = max(3, int(window_size))
    links = np.abs(np.diag(corr, k=1))

    # Pad so the convolved profile aligns with band indices.
    pad_left = win // 2
    pad_right = win - 1 - pad_left
    padded = np.pad(links, (pad_left, pad_right + 1), mode="edge")
    kernel = np.ones(win, dtype=np.float64)
    return np.convolve(padded, kernel, mode="same")[:n_bands]


def _corr_diff_breaks(corr, threshold, window_size, min_bands):
    """Return band indices where a new segment starts."""
    n_bands = corr.shape[0]
    if window_size is None:
        window_size = max(5, n_bands // 20)

    profile = _window_profile(corr, window_size)
    diffs = np.abs(np.diff(profile))
    if diffs.size == 0:
        return []

    max_diff = float(diffs.max())
    score = max_diff * threshold
    breaks = [i + 1 for i, diff in enumerate(diffs) if diff > score]
    return _merge_short_segments(breaks, n_bands, min_bands)


def _merge_short_segments(breaks, n_bands, min_bands):
    """Drop breaks that would create regions shorter than min_bands."""
    bounds = [0] + sorted(set(breaks)) + [n_bands]

    changed = True
    while changed and len(bounds) > 2:
        changed = False
        sizes = [bounds[i + 1] - bounds[i] for i in range(len(bounds) - 1)]
        short_idx = next((i for i, size in enumerate(sizes) if size < min_bands), None)
        if short_idx is None:
            break

        changed = True
        if short_idx == 0:
            bounds.pop(1)
        elif short_idx == len(sizes) - 1:
            bounds.pop(-2)
        else:
            left = sizes[short_idx - 1]
            right = sizes[short_idx + 1]
            remove_at = short_idx if left <= right else short_idx + 1
            bounds.pop(remove_at)

    return bounds[1:-1]
