"""Score the complete customer dataset ONCE with the locked pipeline, in batch.

Uses (read-only, never refits or writes):
  * Phase 2 artifact ``predict_proba`` on the whole frame (vectorised),
  * Phase 4 ``BusinessEngine.profile_frame`` (CLV, value at risk, ENB, eligibility, decision, action evaluations),
  * Phase 5 locked segmentation, nearest-centroid ``assign_customers`` on the whole frame.

The ``ml`` imports are deliberately local to ``ArtifactPortfolioProvider._build`` so the rest of this package (and
its tests) work without the Phase 1-5 stack.
"""
from __future__ import annotations

import hashlib
import logging
import threading
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Protocol

from retention.errors import PortfolioUnavailableError
from retention.models import ActionOption, Portfolio, ScoredCustomer

logger = logging.getLogger("trichurn.retention")


class PortfolioProvider(Protocol):
    """Anything that can supply the scored portfolio (the real artifact-based one, or a test double)."""

    def get(self) -> Portfolio: ...

    def is_loaded(self) -> bool: ...


def sha256_of(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def build_portfolio(customers: list[ScoredCustomer], **meta: Any) -> Portfolio:
    """Assemble a ``Portfolio``; rejects duplicate customer ids (they would silently shadow each other)."""
    index = {c.customer_id: c for c in customers}
    if len(index) != len(customers):
        raise PortfolioUnavailableError("duplicate_customer_ids")
    return Portfolio(customers=tuple(customers), index=index, **meta)


@dataclass(frozen=True)
class ScoringSources:
    """Locations and pins used to build the portfolio. Mirrors the Phase 6 settings; nothing is hard-coded."""
    phase2_model: Path
    phase2_expected_sha256: str | None
    phase5_model: Path
    phase5_expected_sha256: str | None
    dataset_csv: Path
    dataset_spec: Path


class ArtifactPortfolioProvider:
    """Builds the portfolio lazily, once, thread-safely. Failures are reported as ``PortfolioUnavailableError``
    with a short reason code; a failed build is retried on the next call (e.g. after a file is restored)."""

    def __init__(self, sources: ScoringSources, clock: Callable[[], datetime] | None = None):
        self._sources = sources
        self._clock = clock or (lambda: datetime.now(UTC))
        self._lock = threading.Lock()
        self._portfolio: Portfolio | None = None

    def is_loaded(self) -> bool:
        return self._portfolio is not None

    def get(self) -> Portfolio:
        with self._lock:
            if self._portfolio is None:
                try:
                    self._portfolio = self._build()
                except PortfolioUnavailableError:
                    raise
                except ImportError as exc:
                    logger.warning("Phase 1-5 modules not importable (%s)", type(exc).__name__)
                    raise PortfolioUnavailableError("modules_not_importable") from exc
                except Exception as exc:  # noqa: BLE001 - details stay in the server log
                    logger.error("Portfolio build failed (%s)", type(exc).__name__, exc_info=exc)
                    raise PortfolioUnavailableError("portfolio_build_failed") from exc
            return self._portfolio

    # --------------------------------------------------------------------------------------------- build
    def _build(self) -> Portfolio:
        import pandas as pd

        from ml.business import BusinessEngine, load_business_config
        from ml.pipelines.serialization import load_artifact
        from ml.segmentation import assign_customers, load_verified_segmentation_artifact

        src = self._sources
        for path, code in ((src.phase2_model, "phase2_model_missing"), (src.phase5_model, "phase5_model_missing"),
                           (src.dataset_csv, "dataset_missing"), (src.dataset_spec, "dataset_spec_missing")):
            if not path.is_file():
                raise PortfolioUnavailableError(code)

        model_sha = sha256_of(src.phase2_model)
        if src.phase2_expected_sha256 is not None and model_sha != src.phase2_expected_sha256:
            raise PortfolioUnavailableError("phase2_sha256_mismatch")          # fail closed: never load a changed file
        artifact = load_artifact(src.phase2_model)
        seg = load_verified_segmentation_artifact(src.phase5_model, expected_sha256=src.phase5_expected_sha256)

        spec = _read_spec(src.dataset_spec)
        raw = pd.read_csv(src.dataset_csv)
        id_col = spec["id_column"]
        features = list(artifact.metadata["feature_names"])
        missing = [c for c in [id_col, *features] if c not in raw.columns]
        if missing:
            raise PortfolioUnavailableError("dataset_columns_missing")
        frame = raw[features].copy()
        # a blank TotalCharges string becomes missing, exactly as in training
        frame["TotalCharges"] = pd.to_numeric(frame["TotalCharges"], errors="coerce")
        ids = raw[id_col].astype(str).tolist()

        probabilities = artifact.predict_proba(frame)                                   # Phase 2, whole frame
        config = load_business_config()
        engine = BusinessEngine(config, float(artifact.threshold))
        profiles = engine.profile_frame(frame, probabilities, None)                     # Phase 4
        assignments = assign_customers(seg.model, seg.segment_names, frame, None)       # Phase 5, nearest centroid

        customers: list[ScoredCustomer] = []
        for cid, (_, row), profile, assignment in zip(ids, frame.iterrows(), profiles, assignments, strict=True):
            customers.append(ScoredCustomer(
                customer_id=cid, churn_probability=float(profile.churn_probability), risk_band=str(profile.risk_band),
                segment_id=int(assignment.segment_id), segment_name=str(assignment.segment_name),
                clv=float(profile.clv), value_at_risk=float(profile.value_at_risk),
                decision=str(profile.intervention_decision), recommended_action_id=str(profile.recommended_action_id),
                recommended_action=str(profile.recommended_action), action_cost=float(profile.action_cost),
                action_success_rate=float(profile.action_success_rate),
                expected_benefit=float(profile.expected_benefit),
                expected_net_benefit=float(profile.expected_net_benefit),
                decision_reasons=tuple(str(m) for m in profile.decision_reason_messages),
                options=tuple(ActionOption(
                    e.action.action_id, e.action.name, float(e.action.cost), float(e.action.success_rate),
                    bool(e.eligible), e.ineligible_reason, float(e.enb.expected_benefit),
                    float(e.enb.expected_net_benefit)) for e in profile.action_evaluations),
                features={k: _plain(v) for k, v in row.to_dict().items()}))

        catalogue = tuple(ActionOption(a.action_id, a.name, float(a.cost), float(a.success_rate), a.enabled, None,
                                       0.0, 0.0) for a in config.actions.values())
        return build_portfolio(
            customers, currency_code=config.currency.code, currency_symbol=config.currency.symbol,
            model_version=str(artifact.metadata["model_version"]), model_sha256=model_sha,
            segmentation_version=str(seg.metadata["model_version"]), segmentation_sha256=seg.sha256,
            dataset_sha256=sha256_of(src.dataset_csv), dataset_columns=tuple(str(c) for c in raw.columns),
            decision_threshold=float(artifact.threshold),
            scored_at=self._clock().isoformat(timespec="seconds"), action_catalogue=catalogue)


def _plain(value: Any) -> Any:
    """JSON-friendly scalar (numpy -> python, NaN -> None)."""
    if hasattr(value, "item"):
        value = value.item()
    if isinstance(value, float) and value != value:
        return None
    return value


def _read_spec(path: Path) -> dict[str, Any]:
    import yaml

    spec = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(spec, dict) or "id_column" not in spec:
        raise PortfolioUnavailableError("dataset_spec_invalid")
    return spec
