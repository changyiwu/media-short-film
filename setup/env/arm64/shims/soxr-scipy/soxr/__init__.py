"""soxr stand-in: only resample(), implemented with scipy.signal.resample_poly. See ../pyproject.toml for why."""
from fractions import Fraction

import numpy as np

__version__ = "0.0.0+scipy"
QQ, LQ, MQ, HQ, VHQ = "QQ", "LQ", "MQ", "HQ", "VHQ"


def resample(x, in_rate, out_rate, quality="HQ"):
    """Same call shape as soxr.resample: x is 1-D (frames) or 2-D (frames, channels); returns the input dtype."""
    from scipy.signal import resample_poly
    x = np.asarray(x)
    if in_rate == out_rate:
        return x.copy()
    r = Fraction(int(round(out_rate)), int(round(in_rate))).limit_denominator(1000)
    y = resample_poly(x.astype(np.float64), r.numerator, r.denominator, axis=0)
    return y.astype(x.dtype if np.issubdtype(x.dtype, np.floating) else np.float32)
