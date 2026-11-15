"""Map a churn probability to a configured risk band (single band system; thresholds live in risk_bands.yaml)."""
from __future__ import annotations

from typing import Any

from ml.business.schemas import RiskBand
from ml.business.validation import require_probability


def assign_risk_band(churn_probability: Any, bands: tuple[RiskBand, ...]) -> str:
    """Name of the last band whose ``min_probability`` is <= the probability."""
    p = require_probability(churn_probability)
    name = bands[0].name
    for band in bands:
        if p >= band.min_probability:
            name = band.name
    return name
