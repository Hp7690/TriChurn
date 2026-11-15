"""Test support for Phase 9. Builds a SYNTHETIC portfolio (tests only) using the real Phase 4 business engine, so the
tests exercise the same decision/ENB code as production without needing the model artifacts."""
from __future__ import annotations

from retention.models import ActionOption, Portfolio, ScoredCustomer
from retention.scoring import build_portfolio

CONTRACTS = ("Month-to-month", "One year", "Two year")


def _profile_customers(n: int):
    from ml.business import BusinessEngine, load_business_config

    config = load_business_config()
    engine = BusinessEngine(config, 0.34)
    rows = []
    for i in range(n):
        p = round(0.02 + 0.96 * ((i * 37) % n) / max(n - 1, 1), 4)          # deterministic spread over 0.02-0.98
        record = {"MonthlyCharges": 20.0 + (i * 13) % 100, "Contract": CONTRACTS[i % 3], "tenure": 1 + i % 72}
        rows.append((f"T-{i:04d}", p, record, engine.profile(p, record, f"T-{i:04d}"), i % 3))
    return config, rows


def make_portfolio(n: int = 60) -> Portfolio:
    config, rows = _profile_customers(n)
    customers = []
    for cid, _p, record, prof, seg in rows:
        customers.append(ScoredCustomer(
            customer_id=cid, churn_probability=prof.churn_probability, risk_band=prof.risk_band, segment_id=seg,
            segment_name=("Low Value / High Risk", "Low Value / Stable", "High Value / Stable")[seg], clv=prof.clv,
            value_at_risk=prof.value_at_risk, decision=prof.intervention_decision,
            recommended_action_id=prof.recommended_action_id, recommended_action=prof.recommended_action,
            action_cost=prof.action_cost, action_success_rate=prof.action_success_rate,
            expected_benefit=prof.expected_benefit, expected_net_benefit=prof.expected_net_benefit,
            decision_reasons=tuple(prof.decision_reason_messages),
            options=tuple(ActionOption(e.action.action_id, e.action.name, e.action.cost, e.action.success_rate,
                                       e.eligible, e.ineligible_reason, e.enb.expected_benefit,
                                       e.enb.expected_net_benefit) for e in prof.action_evaluations),
            features=dict(record)))
    catalogue = tuple(ActionOption(a.action_id, a.name, a.cost, a.success_rate, a.enabled, None, 0.0, 0.0)
                      for a in config.actions.values())
    return build_portfolio(
        customers, currency_code=config.currency.code, currency_symbol=config.currency.symbol,
        model_version="test", model_sha256="0" * 64, segmentation_version="test", segmentation_sha256="1" * 64,
        dataset_sha256="2" * 64, dataset_columns=("customerID", "tenure", "Churn"), decision_threshold=0.34,
        scored_at="2025-01-01T00:00:00+00:00", action_catalogue=catalogue)


class StaticProvider:
    """PortfolioProvider test double."""

    def __init__(self, portfolio: Portfolio | None = None, error: Exception | None = None):
        self._portfolio, self._error, self.loads = portfolio, error, 0

    def get(self) -> Portfolio:
        self.loads += 1
        if self._error is not None:
            raise self._error
        assert self._portfolio is not None
        return self._portfolio

    def is_loaded(self) -> bool:
        return self.loads > 0
