"""Retention-action evaluation and selection. Costs and success rates come from configuration only."""
from __future__ import annotations

from collections.abc import Mapping

from ml.business.enb import compute_enb
from ml.business.schemas import NO_ACTION_ID, ActionEvaluation, RetentionAction


def evaluate_action(action: RetentionAction, clv: float, churn_probability: float,
                    max_action_cost: float | None = None) -> ActionEvaluation:
    """ENB components plus eligibility under the action's own ``min_clv`` and the policy's cost cap."""
    enb = compute_enb(clv, churn_probability, action.success_rate, action.cost)
    reason = None
    if action.min_clv is not None and clv < action.min_clv:
        reason = f"customer value {clv:.2f} is below this action's minimum {action.min_clv:.2f}"
    elif max_action_cost is not None and action.cost > max_action_cost:
        reason = f"action cost {action.cost:.2f} exceeds the per-customer cap {max_action_cost:.2f}"
    return ActionEvaluation(action, reason is None, reason, enb)


def evaluate_actions(actions: Mapping[str, RetentionAction], clv: float, churn_probability: float,
                     max_action_cost: float | None = None) -> tuple[ActionEvaluation, ...]:
    """Evaluate every ENABLED action in configuration order. Disabled actions are ignored entirely.

    ``no_action`` is always eligible and exempt from the cost cap (its cost is 0)."""
    out = []
    for action in actions.values():
        if not action.enabled:
            continue
        ev = evaluate_action(action, clv, churn_probability, max_action_cost)
        out.append(ev if action.action_id != NO_ACTION_ID else ActionEvaluation(action, True, None, ev.enb))
    return tuple(out)


def best_by_enb(evaluations: tuple[ActionEvaluation, ...]) -> ActionEvaluation | None:
    """Highest-ENB eligible non-``no_action`` option regardless of sign (for reporting economics, not for choosing)."""
    pool = [e for e in evaluations if e.action.action_id != NO_ACTION_ID and e.eligible]
    return min(pool, key=lambda e: (-e.enb.expected_net_benefit, e.enb.action_cost, e.action.action_id), default=None)


def select_best_action(evaluations: tuple[ActionEvaluation, ...],
                       min_expected_net_benefit: float) -> ActionEvaluation | None:
    """Highest-ENB eligible action whose ENB is strictly above the policy minimum; None if there is none.

    ``no_action`` is never 'selected' here (it is the fallback). Ties: higher ENB, then lower cost, then action_id,
    so the result never depends on dictionary order."""
    candidates = [e for e in evaluations
                  if e.action.action_id != NO_ACTION_ID and e.eligible
                  and e.enb.expected_net_benefit > min_expected_net_benefit]
    if not candidates:
        return None
    return min(candidates, key=lambda e: (-e.enb.expected_net_benefit, e.enb.action_cost, e.action.action_id))
