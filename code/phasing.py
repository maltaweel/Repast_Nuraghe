"""Phased construction (specified by the authors): start with a fraction `frac` of the nuraghi; the next fraction starts
only once ALL nuraghi of the previous phase are built; repeat until 100%. P10 = 0.1 (10 phases), P20 = 0.2 (5).

Cohort membership is a random order per seed, drawn from its own stream default_rng([seed, PHASE_STREAM]) so that it
never touches any model random stream, and is identical in every scenario with the same site list (common random
numbers: the post hoc P10 of `full` and the simulated P10 of `high` / A5_full use the same cohorts for a seed).
Phase k (0-based) holds order[bounds[k]:bounds[k+1]] with bounds = floor(k * N / n_phases).
"""
import re

import numpy as np

PHASE_STREAM = 4242


def n_phases(frac):
    k = int(round(1.0 / float(frac)))
    assert k >= 1 and abs(k * float(frac) - 1.0) < 1e-9, f"phase fraction must be 1/k, got {frac}"
    return k


def cohorts(n, frac, seed):
    """List of index arrays (positions 0..n-1 in site order), one per phase."""
    order = np.random.default_rng([int(seed), PHASE_STREAM]).permutation(n)
    k = n_phases(frac)
    b = (np.arange(k + 1) * n) // k
    return [np.sort(order[b[j]:b[j + 1]]) for j in range(k)]


def phase_of(n, frac, seed):
    """Per site (site order) its phase number 0..k-1."""
    ph = np.zeros(n, np.int64)
    for j, c in enumerate(cohorts(n, frac, seed)):
        ph[c] = j
    return ph


def split_name(name):
    """'high_P10' -> ('high', 0.1); 'A5_full_P20' -> ('A5_full', 0.2); 'full' -> ('full', None)."""
    if name is None:
        return None, None
    m = re.fullmatch(r"(.+)_P(\d+)", name)
    if not m:
        return name, None
    return m.group(1), int(m.group(2)) / 100.0
