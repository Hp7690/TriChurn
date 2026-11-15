"""Numerical safety for the business layer: every monetary / probability input passes through here.

Rejects bool, strings, None, NaN and +/-inf instead of coercing them; raises ``BusinessInputError`` with a message
that names the offending field. Returns a plain ``float`` so downstream arithmetic is deterministic.
"""
from __future__ import annotations

import math
import numbers
from typing import Any

from ml.errors import BusinessInputError


def require_finite(value: Any, name: str) -> float:
    """A real, finite number (bool is rejected: ``True`` is not a probability)."""
    if isinstance(value, bool) or not isinstance(value, numbers.Real):
        raise BusinessInputError(f"{name} must be a number, got {value!r} ({type(value).__name__}).")
    out = float(value)
    if not math.isfinite(out):
        raise BusinessInputError(f"{name} must be finite, got {out}.")
    return out


def require_probability(value: Any, name: str = "churn_probability") -> float:
    """0 <= value <= 1."""
    out = require_finite(value, name)
    if not 0.0 <= out <= 1.0:
        raise BusinessInputError(f"{name} must be between 0 and 1, got {out}.")
    return out


def require_rate(value: Any, name: str = "success_rate") -> float:
    """0 <= value <= 1 (success rates, margins, shares)."""
    return require_probability(value, name)


def require_non_negative(value: Any, name: str) -> float:
    """value >= 0 (costs, revenue, CLV, thresholds expressed in money)."""
    out = require_finite(value, name)
    if out < 0.0:
        raise BusinessInputError(f"{name} must be >= 0, got {out}.")
    return out
