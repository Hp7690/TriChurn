"""Config-driven feature engineering, implemented as an sklearn transformer.

Rules: (1) only uses columns present in X (it never sees the target), (2) anything
learned (quantile edges) is learned in fit() so it is fitted on training folds only,
(3) a feature whose inputs are missing is skipped and reported, never faked.
"""
from __future__ import annotations

import numpy as np
import pandas as pd
from sklearn.base import BaseEstimator, TransformerMixin

FEATURE_DOCS: dict[str, str] = {
    "tenure_group": "Tenure bucket (0-12, 13-24, 25-48, 49+ months). Needs: tenure.",
    "monthly_charge_band": "Quartile band of monthly charges; edges learned from training data only. "
                           "Needs: monthly_charges.",
    "service_count": "Number of subscribed services (affirmative values). Needs: service_columns.",
    "protective_service_count": "Number of protective/support services (security, backup, "
                                "protection, tech support). Needs: protective_columns.",
    "contract_risk": "Ordinal contract commitment prior (month-to-month=2 ... two-year=0), from config; "
                     "not learned from the target. Needs: contract.",
    "payment_risk": "Payment-friction prior (manual/electronic=1, automatic/other=0), from config. "
                    "Needs: payment_method.",
    "monthly_vs_avg_charge_delta": "Current monthly charge minus lifetime average monthly charge "
                                   "(total/tenure); positive = price rose. Needs: monthly_charges, "
                                   "total_charges, tenure.",
    "support_calls_per_month": "Support calls divided by tenure months. Needs: support_calls, tenure.",
}


def _num(s: pd.Series) -> pd.Series:
    out = pd.to_numeric(s, errors="coerce")
    return out.replace([np.inf, -np.inf], np.nan)


class FeatureEngineer(BaseEstimator, TransformerMixin):
    def __init__(self, config: dict | None = None):
        self.config = config

    # -- helpers ---------------------------------------------------------
    def _roles(self) -> dict:
        return (self.config or {}).get("roles", {})

    def _col(self, X: pd.DataFrame, role: str) -> str | None:
        c = self._roles().get(role)
        return c if c and c in X.columns else None

    def _cols(self, X: pd.DataFrame, role: str) -> list[str]:
        return [c for c in (self._roles().get(role) or []) if c in X.columns]

    def _count_yes(self, X: pd.DataFrame, cols: list[str]) -> pd.Series:
        yes = set((self.config or {}).get("affirmative_values", ["yes", "true", "1"]))
        flags = [X[c].map(lambda v: str(v).strip().lower() in yes if pd.notna(v) else False) for c in cols]
        return pd.concat(flags, axis=1).sum(axis=1).astype("float64")

    # -- sklearn API -----------------------------------------------------
    def fit(self, X: pd.DataFrame, y=None):
        self.edges_: list[float] = []
        mc = self._col(X, "monthly_charges")
        if mc is not None:
            q = (self.config or {}).get("charge_band_quantiles", 4)
            vals = _num(X[mc]).dropna().to_numpy()
            if len(vals) >= q:
                qs = np.linspace(0, 1, q + 1)[1:-1]
                self.edges_ = sorted(set(float(e) for e in np.quantile(vals, qs)))
        self.created_, self.skipped_ = self._plan(X)
        return self

    def _plan(self, X: pd.DataFrame) -> tuple[list[str], dict[str, str]]:
        created, skipped = [], {}

        def need(feature: str, ok: bool, why: str) -> None:
            if ok:
                created.append(feature)
            else:
                skipped[feature] = why

        need("tenure_group", self._col(X, "tenure") is not None, "no tenure column")
        need("monthly_charge_band",
             self._col(X, "monthly_charges") is not None and bool(self.edges_),
             "no monthly_charges column (or too little data)")
        need("service_count", bool(self._cols(X, "service_columns")), "no service columns")
        need("protective_service_count", bool(self._cols(X, "protective_columns")),
             "no protective-service columns")
        need("contract_risk", self._col(X, "contract") is not None, "no contract column")
        need("payment_risk", self._col(X, "payment_method") is not None, "no payment-method column")
        need("monthly_vs_avg_charge_delta",
             all(self._col(X, r) for r in ("monthly_charges", "total_charges", "tenure")),
             "needs monthly_charges, total_charges and tenure")
        need("support_calls_per_month",
             all(self._col(X, r) for r in ("support_calls", "tenure")),
             "needs support_calls and tenure")
        return created, skipped

    def transform(self, X: pd.DataFrame) -> pd.DataFrame:
        out = X.copy()
        cfg = self.config or {}
        ten = self._col(X, "tenure")
        if "tenure_group" in self.created_:
            b = cfg.get("tenure_bins", [12, 24, 48])
            labels = [f"0-{b[0]}m"] + [f"{b[i] + 1}-{b[i + 1]}m" for i in range(len(b) - 1)] + [f"{b[-1] + 1}m+"]
            out["tenure_group"] = pd.cut(
                _num(X[ten]), bins=[-np.inf, *b, np.inf], labels=labels
            ).astype(object)
        if "monthly_charge_band" in self.created_:
            mc = self._col(X, "monthly_charges")
            labels = [f"Q{i + 1}" for i in range(len(self.edges_) + 1)]
            out["monthly_charge_band"] = pd.cut(
                _num(X[mc]), bins=[-np.inf, *self.edges_, np.inf], labels=labels
            ).astype(object)
        if "service_count" in self.created_:
            out["service_count"] = self._count_yes(X, self._cols(X, "service_columns"))
        if "protective_service_count" in self.created_:
            out["protective_service_count"] = self._count_yes(X, self._cols(X, "protective_columns"))
        if "contract_risk" in self.created_:
            m = cfg.get("contract_risk", {})
            col = X[self._col(X, "contract")]
            out["contract_risk"] = col.map(lambda v: m.get(str(v).strip(), np.nan)).astype("float64")
        if "payment_risk" in self.created_:
            m = cfg.get("payment_risk", {})
            col = X[self._col(X, "payment_method")]
            out["payment_risk"] = col.map(lambda v: m.get(str(v).strip(), np.nan)).astype("float64")
        if "monthly_vs_avg_charge_delta" in self.created_:
            mc, tc = _num(X[self._col(X, "monthly_charges")]), _num(X[self._col(X, "total_charges")])
            t = _num(X[ten])
            avg = tc / t.where(t > 0)
            out["monthly_vs_avg_charge_delta"] = (mc - avg).where(t > 0, 0.0)
        if "support_calls_per_month" in self.created_:
            calls = _num(X[self._col(X, "support_calls")])
            t = _num(X[ten])
            out["support_calls_per_month"] = (calls / t.clip(lower=1))
        return out
