# Phase 4 - Business intelligence and intervention decisioning

Scope: turn the locked model's churn probability into a **business decision** under explicit, configurable
assumptions: customer value, value at risk, retention-action economics, an intervene / do-not-intervene decision with
reasons, and a what-if simulator. Nothing in Phases 1-3 is changed: the model, calibration, threshold, splits, seeds
and SHAP code are untouched, and the model artifact is only read.
Code: `ml/business/` (pure Python; no FastAPI, backend, database, sklearn or shap imports). Config:
`configs/business.yaml`, `configs/risk_bands.yaml`. Tests: `tests/unit/test_business_*.py`,
`tests/integration/test_business_real_model.py`. Demo: `python scripts/run_phase4.py` (`make business`).

```text
customer record + model probability
   -> CLV -> value at risk -> per-action ENB -> eligibility / best action -> policy gates -> decision + reasons
```

## 1. What this is - and is not (non-causal interpretation)
Every success rate, cost, lifetime and threshold is a **business assumption** in a YAML file, not something learned from
data. The outputs are *estimates under those assumptions*. They do not establish that any action prevents churn, and
SHAP values (Phase 3) describe the model's score, not causes. Wording used everywhere: *"Under the configured
success-rate assumption, this action has an estimated expected net benefit of ..."*.
**What-if simulation estimates outcomes under configurable assumptions. It does not establish causal treatment effects.**

## 2. Customer lifetime value (baseline, config-driven)
```text
CLV = revenue_multiplier * gross_margin * monthly_revenue * discounted_months(L, d)

discounted_months(L, d) = L                          if d = 0
                        = (1 - (1 + d)^(-L)) / d     if d > 0      ( = sum_{t=1..L} (1+d)^(-t) )
```
* `monthly_revenue` is the customer's `clv.revenue_field` (Telco: `MonthlyCharges`, the dataset spec's `value_column`).
  It is **required**: a missing/blank/NaN value raises `BusinessInputError`; it is never imputed or guessed.
* `L` is an **assumed remaining lifetime in months**, looked up from `clv.lifetime_segment_field` (Telco: `Contract`)
  in `lifetime_months_by_segment` (illustrative: Month-to-month 12, One year 24, Two year 36). If the segment value is
  missing or unlisted, `default_lifetime_months` is used **only if** `allow_default_lifetime: true`, and the result
  records `lifetime_source` (`segment:<value>` or `default`). Set it to `false` to fail instead.
* Defaults give the plain baseline `CLV = MonthlyCharges x assumed lifetime` (`gross_margin: 1.0`, `d = 0`).
* This is **not** a survival/CLV model and not a causal lifetime estimate; the dataset (one snapshot, no billing
  history) does not support one. Replace the lifetime table with your own figures.

## 3. Value at Risk
```text
value_at_risk = CLV x churn_probability
```
An expected-risk figure (model probability x assumed value), not a causal estimate. Its quality depends on how well
calibrated the locked model's probabilities are (see `docs/phase2.md`).

## 4. Expected Net Benefit (ENB)
```text
expected_benefit     = value_at_risk x action_success_rate
expected_cost        = action_cost                      (paid with certainty once the action is taken)
expected_net_benefit = expected_benefit - expected_cost
                     = CLV x churn_probability x action_success_rate - action_cost
```
`ml/business/enb.py` exposes one function per line and `compute_enb` returns every component
(`clv, churn_probability, value_at_risk, action_success_rate, action_cost, expected_benefit, expected_cost,
expected_net_benefit`) so the calculation can be audited. Modelling assumptions: the action's success rate applies to
the value at risk; one action per customer; actions are evaluated independently; no budget optimisation across
customers.

## 5. Retention actions (`configs/business.yaml: actions`)
Each action has `action_id` (the key), `name`, `cost`, `success_rate`, `description`, `enabled`, and optionally
`min_clv` (eligible only if CLV >= it). Provided: `no_action`, `retention_email`, `loyalty_offer`, `priority_support`,
`discount_offer`, `personalized_offer`. `no_action` is mandatory, enabled, cost 0, success rate 0 (validated at load).
All numbers are illustrative and on the **Telco data's own monetary scale**.

## 6. Action selection
For one customer: evaluate every **enabled** action (disabled ones are ignored entirely), mark ineligible those below
their `min_clv` or above `policy.max_action_cost`, then pick the eligible non-`no_action` action with the highest
ENB **strictly greater than** `policy.min_expected_net_benefit`. Ties: higher ENB, then lower cost, then `action_id`
(result never depends on config order). No such action => `no_action`. Negative-ENB actions are never recommended.

## 7. Intervention policy (`configs/business.yaml: policy`)
```text
INTERVENE  iff  churn_probability >= min_churn_probability
            AND CLV               >= min_customer_value
            AND best eligible action's ENB > min_expected_net_benefit
otherwise DO_NOT_INTERVENE (recommended action: no_action)
```
`min_churn_probability: model_threshold` (default) reuses the locked model's operating threshold (0.34, from the
artifact) instead of creating a second competing cut-off; a number in [0,1] overrides it. Every failed check is
returned as a structured reason (`CHURN_PROBABILITY_BELOW_MINIMUM`, `CUSTOMER_VALUE_BELOW_MINIMUM`,
`NO_ACTION_WITH_ENB_ABOVE_MINIMUM`); an INTERVENE lists the four passed checks. `format_profile` / `render_reason`
turn reasons into text (presentation is separate from the calculation).

## 8. Risk bands (`configs/risk_bands.yaml`)
Phases 1-3 had no risk-band system, so this is the single one: `LOW 0.00`, `MEDIUM 0.20`, `HIGH 0.50`,
`CRITICAL 0.75` (lower edge inclusive; first band must start at 0; strictly increasing). Illustrative thresholds,
not model outputs.

## 9. Customer business profile
`BusinessEngine(config, model_threshold).profile(probability, record, customer_id)` returns a frozen
`CustomerBusinessProfile`: `customer_id, churn_probability, risk_band, clv, value_at_risk, recommended_action(_id),
action_cost, action_success_rate, expected_benefit, expected_cost, expected_net_benefit, intervention_decision,
decision_reasons` plus `clv_detail`, every `action_evaluations` row and the resolved `policy`. `profile_frame` scores
a DataFrame with probabilities from `ModelArtifact.predict_proba`. The probability is an **input**; this layer never
loads, re-scores or modifies the model.

## 10. Model explanation vs business decision
`engine.explain(profile, local_explanation)` returns two separate sections: **MODEL EXPLANATION** (top features that
contributed toward a higher/lower *model score*, from the Phase 3 `LocalExplanation`, duck-typed so `shap` is not
imported) and **BUSINESS DECISION** (the ENB reasoning under assumptions), plus the non-causal disclaimer.

## 11. What-if simulation (`SIMULATION / WHAT-IF`)
`simulate(config, churn_probability, clv, Scenario(...), model_threshold)` recomputes ENB, decision and recommended
action under changed assumptions: `churn_probability`, `clv`, per-action `action_cost` / `action_success_rate`,
`min_churn_probability`, `min_customer_value`, `min_expected_net_benefit`. It returns baseline, scenario and deltas.
`economics` is the best eligible action's ENB **even when negative or policy-blocked**, so a cost increase shows its
true effect. `sweep_churn_probability` and `sweep_multiplier` use the grids in `what_if.sweeps`. It does not retrain,
touch the model/dataset, or change decisions in production: configs are frozen dataclasses and every override is
applied to a copy. `no_action` cannot be overridden.

## 12. Validation, determinism, configuration
* Probabilities and rates must be in [0,1]; costs, revenue, CLV >= 0; NaN, +/-inf, None, bool and numeric strings are
  rejected with `BusinessInputError` (config problems raise `BusinessConfigError`). Both subclass `TriChurnError`.
  A missing revenue value (None, blank, `float`/`numpy` NaN, `pd.NA`) always gets the same "is required ... and is
  missing" message.
* Config flags (`actions.<id>.enabled`, `clv.allow_default_lifetime`) must be real YAML booleans. A quoted
  `"false"` is rejected (Python's `bool("false")` is `True`, which used to silently re-enable a disabled action), and an
  action entry that is not a mapping raises `BusinessConfigError` instead of an `AttributeError`.
* No randomness anywhere in `ml/business`; identical inputs give identical outputs (tested).
* Currency (`INR` by default) is a label used only for formatting; **no FX conversion** happens. Telco amounts are used
  as-is unless you set `clv.revenue_multiplier`. Action costs and `min_customer_value` must be on the same scale.

## 13. Example (real run: `python scripts/run_phase4.py`, first 500 TRAIN customers, locked model, threshold 0.34)
```text
decisions: DO_NOT_INTERVENE 344, INTERVENE 156   risk bands: LOW 256, MEDIUM 137, HIGH 84, CRITICAL 23
recommended actions (treated): discount_offer 131, loyalty_offer 18, retention_email 7

Customer ID: 9497-QCMMS
Churn Probability: 0.88   Risk Band: CRITICAL
CLV: ₹1,122.60   Value at Risk: ₹988.49
Recommended Action: Discount offer
Action Cost: ₹60.00   Assumed Success Rate: 0.25
Expected Benefit: ₹247.12   Expected Net Benefit: ₹187.12
Decision: INTERVENE
```
This is an illustration on TRAIN rows (in-sample for the model), not an evaluation, and the TEST split is never read.
The ₹ symbol is presentation only; amounts are Telco's own units.

## 14. Tests
`pytest -rs`; Phase 4 only: `pytest -rs tests/unit/test_business_*.py tests/integration/test_business_*.py`
(354 tests; no skips when `make data` has been run and `models/` is present).
Covers CLV (normal/zero/boundary/invalid/missing), value at risk, ENB (positive/zero/negative/zero-cost) and 200
seeded invariant cases (ENB rises with success rate, falls with cost; VaR rises with probability and CLV), action
selection (best, negative rejected, disabled ignored, none profitable, min_clv, cost cap, ties), the intervention
policy gates and boundaries, risk bands from config, profile consistency, what-if effects and non-mutation, numerical
validation, config validation, determinism, an AST guard (no web/db/model/random imports; no hard-coded currency or
business constants in logic), config hardening regressions (`test_business_config_hardening.py`), and integration runs on
the locked artifact and the real Telco CSV (model bytes verified unchanged). `test_business_independent_recompute.py`
recomputes CLV, value at risk, ENB, decision and action for 400 real customers with plain arithmetic from the YAML and
the CSV (without calling `ml.business`), checks that the business layer consumed the locked model's own probability
(no second churn model), and runs `scripts/run_phase4.py` end to end.

**Fixes made during the Phase 4/5 audit** (each has a regression test in `test_business_config_hardening.py`):
(1) `enabled` and `clv.allow_default_lifetime` must be real YAML booleans. `bool("false")` is `True`, so a quoted
`enabled: "false"` used to silently re-enable a disabled, costly action; it now raises `BusinessConfigError`.
(2) A non-mapping action entry now raises `BusinessConfigError` instead of a raw `AttributeError`.
(3) Missing revenue given as `pd.NA` or a NumPy NaN now gets the documented "is missing" error. No calculation,
formula, default or policy changed.

**Data dependency.** The integration tests need `ml/data/raw/telco_churn.csv` (`make data`) and the locked artifact in
`models/`. Without the CSV they skip with the reason "needs models/ and `make data`"; that is a missing dependency, not a
pass. Run `make data` first.

## 15. Limitations
Lifetimes, costs, success rates and thresholds are placeholders you must replace; success rates are not estimated from
experiments, so ENB can rank actions only as well as those assumptions hold; CLV ignores churn hazard, upsell and
discounting unless configured; actions are not combined and there is no portfolio/budget optimisation; probabilities
are taken as-is from the locked model; one-snapshot Telco data has no billing history or cost data. A real
programme would estimate success rates from randomized retention tests (uplift modelling), which is out of scope here.
