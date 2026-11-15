"""Forecast model interface, a transparent seasonal-naive baseline, and a backtest report structure.

Only runs on a series that ``validate`` returned as FORECAST_READY and without gaps. Results are labelled baseline
evaluation, not a validated business forecast.
"""
from __future__ import annotations

from typing import Any, Protocol

import numpy as np
import pandas as pd


class ForecastModel(Protocol):
    name: str

    def fit(self, series: pd.Series) -> None: ...

    def predict(self, horizon: int) -> list[float]: ...


class NaiveLastValue:
    name = "naive_last_value"

    def fit(self, series: pd.Series) -> None:
        self._last = float(series.iloc[-1])

    def predict(self, horizon: int) -> list[float]:
        return [self._last] * horizon


class SeasonalNaive:
    """Repeat the value from 12 periods earlier (requires >= 12 observations)."""
    name = "seasonal_naive_12"

    def fit(self, series: pd.Series) -> None:
        if len(series) < 12:
            raise ValueError("seasonal naive needs at least 12 observations")
        self._tail = [float(x) for x in series.iloc[-12:]]

    def predict(self, horizon: int) -> list[float]:
        return [self._tail[i % 12] for i in range(horizon)]


def evaluate(series: pd.Series, holdout: int, models: list[ForecastModel] | None = None) -> dict[str, Any]:
    """Single hold-out backtest: train on all but the last ``holdout`` periods, score on the hold-out."""
    if series.isna().any():
        return {"status": "UNAVAILABLE", "reason": "Series contains gaps; backtest requires a contiguous series."}
    if len(series) <= holdout + 12:
        return {"status": "UNAVAILABLE", "reason": "Not enough periods for the requested hold-out."}
    train, test = series.iloc[:-holdout], series.iloc[-holdout:]
    results = []
    for m in models or [NaiveLastValue(), SeasonalNaive()]:
        m.fit(train)
        pred = np.array(m.predict(holdout))
        actual = test.to_numpy(dtype=float)
        mae = float(np.mean(np.abs(actual - pred)))
        nz = actual != 0
        mape = float(np.mean(np.abs((actual[nz] - pred[nz]) / actual[nz]))) if nz.any() else None
        results.append({"model": m.name, "mae": round(mae, 4), "mape": None if mape is None else round(mape, 4)})
    return {"status": "ESTIMATED", "method": "single_holdout_backtest", "holdout_periods": holdout,
            "train_periods": int(len(train)), "results": results,
            "note": "Baselines only. A single hold-out is not proof of forecast accuracy."}
