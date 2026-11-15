"""REAL production adapter: connects the API to the locked Phase 1-5 implementation.

THIS IS THE ONLY MODULE IN ``app/`` THAT IMPORTS THE ``ml`` PACKAGE, and only inside ``default_bindings()`` below.

>>> INTEGRATION POINT <<<  ``default_bindings()`` is the single place that names Phase 1-5 functions. If your project
layout differs, change ONLY that function (or provide your own bindings / a ``TRICHURN_ADAPTER_FACTORY``); routes,
services and schemas never change. See ``phase6/INTEGRATION.md``.

What it does per capability (nothing is re-implemented here):
  predict   Phase 2 artifact ``predict_proba`` + stored threshold; risk band from the Phase 4 risk-band config.
  explain   Phase 3 ``ChurnShapExplainer`` (the locked model, 100-row TRAIN background).
  business  Phase 4 ``BusinessEngine.profile`` / ``.explain`` (CLV, VaR, ENB, decision, best action).
  segment   Phase 5 locked artifact, nearest-centroid ``assign`` (NO ``KMeans.fit``, ever).
It never retrains, refits, recalibrates or writes any artifact, and it fails closed: whatever cannot be loaded is
reported by ``readiness()`` and answered with 503, never replaced by defaults or fake output.
"""
from __future__ import annotations

import logging
import threading
from collections.abc import Callable, Iterator, Mapping
from contextlib import contextmanager
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from app.core.config import Settings
from app.core.errors import (
    ApiError,
    artifact_unavailable,
    capability_unavailable,
    integration_not_configured,
    invalid_input,
)
from app.schemas.common import CustomerFeatures
from app.services.adapters.interface import (
    CAP_BUSINESS,
    CAP_EXPLAIN,
    CAP_MODEL,
    CAP_MODULES,
    CAP_SCHEMA,
    CAP_SEGMENT,
    ActionEvaluation,
    BusinessExplanation,
    BusinessResult,
    CheckResult,
    DecisionReason,
    ExplanationResult,
    FeatureContribution,
    PredictionResult,
    ReadinessReport,
    SegmentResult,
)
from app.services.artifact_loader import ArtifactLoader, ArtifactSpec, ArtifactUnavailableError

logger = logging.getLogger("trichurn.api.adapter")

SEGMENT_NOTE = ("Nearest-centroid assignment to the locked Phase 5 segmentation. The distance is a clustering distance "
                "in the scaled feature space, not a probability. Segments are descriptive, not causal.")


# ================================================================================================ bindings
@dataclass(frozen=True)
class Phase15Bindings:
    """Callables that wrap the Phase 1-5 implementation. ``default_bindings()`` builds the standard set."""

    load_churn_artifact: Callable[[Path, str | None], Any]       # (path, pinned sha256) -> verified artifact
    load_dataset_spec: Callable[[Path], Any]
    build_explainer: Callable[[Any, Path, Any], Any]             # (verified artifact, TRAIN csv, spec) -> explainer
    load_business_config: Callable[[], Any]
    make_business_engine: Callable[[Any, float], Any]            # (config, model threshold) -> engine
    assign_risk_band: Callable[[float, Any], str]                # (probability, business config) -> band name
    load_segmentation_artifact: Callable[[Path, str | None], Any]
    assign_segment: Callable[[Any, pd.DataFrame], tuple[int, str, float]]   # -> (segment_id, name, distance)
    translate_error: Callable[[BaseException], ApiError | None]  # domain errors -> client-safe ApiError (or None)


def default_bindings() -> Phase15Bindings:
    """>>> INTEGRATION POINT <<< the real Phase 1-5 imports. Raises ImportError if the ``ml`` package is unavailable."""
    from ml.business import BusinessEngine, assign_risk_band, load_business_config
    from ml.errors import (
        ArtifactIntegrityError,
        BusinessInputError,
        ExplainabilityInputError,
        SegmentationInputError,
    )
    from ml.explainability import ChurnShapExplainer, load_train_background, load_verified_artifact
    from ml.pipelines.ingestion import DatasetSpec
    from ml.segmentation import assign_customers, load_verified_segmentation_artifact

    def build_explainer(verified: Any, csv_path: Path, spec: Any) -> Any:
        return ChurnShapExplainer(verified, load_train_background(csv_path, spec, verified))

    def assign_segment(verified_seg: Any, frame: pd.DataFrame) -> tuple[int, str, float]:
        a = assign_customers(verified_seg.model, verified_seg.segment_names, frame, None)[0]
        return a.segment_id, a.segment_name, a.distance_to_centroid

    def translate_error(exc: BaseException) -> ApiError | None:
        if isinstance(exc, BusinessInputError | ExplainabilityInputError | SegmentationInputError):
            return invalid_input("Invalid customer features.")           # domain text is logged, not returned
        if isinstance(exc, ArtifactIntegrityError):
            return artifact_unavailable("model")
        return None

    return Phase15Bindings(
        load_churn_artifact=lambda path, sha: load_verified_artifact(path, expected_sha256=sha),
        load_dataset_spec=lambda path: DatasetSpec.from_yaml(path),
        build_explainer=build_explainer,
        load_business_config=load_business_config,
        make_business_engine=lambda cfg, threshold: BusinessEngine(cfg, threshold),
        assign_risk_band=lambda p, cfg: assign_risk_band(p, cfg.risk_bands),
        load_segmentation_artifact=lambda path, sha: load_verified_segmentation_artifact(path, expected_sha256=sha),
        assign_segment=assign_segment,
        translate_error=translate_error,
    )


# ================================================================================================== helpers
def _describe(exc: BaseException) -> str:
    """Sanitised, code-like reason for readiness output (never a path or exception text)."""
    if isinstance(exc, ArtifactUnavailableError):
        return f"artifact_{exc.reason}"
    if isinstance(exc, ImportError):
        return "modules_not_importable"
    if isinstance(exc, FileNotFoundError):
        return "file_missing"
    return "load_failed"


def _to_frame(customer: Mapping[str, Any]) -> pd.DataFrame:
    """One-row frame of exactly the supplied features. Only an explicit ``None`` becomes NaN (a missing value, as in
    the training data); nothing is invented."""
    return pd.DataFrame([{k: (np.nan if v is None else v) for k, v in customer.items()}])


@dataclass
class _State:
    checks: list[CheckResult] = field(default_factory=list)
    components: dict[str, Any] = field(default_factory=dict)
    details: dict[str, Any] = field(default_factory=dict)
    modules_ok: bool = False
    schema_ok: bool = False
    bindings: Phase15Bindings | None = None
    business_cfg: Any = None
    specs: dict[str, ArtifactSpec] = field(default_factory=dict)

    def add(self, name: str, ok: bool, detail: str = "ok") -> None:
        self.checks.append(CheckResult(name, ok, detail))


# ==================================================================================================== adapter
class Phase15Adapter:
    """Production implementation of ``Phase15Port`` over the real Phase 1-5 code. Loads lazily, once, thread-safely."""

    is_test_double = False

    def __init__(self, settings: Settings, loader: ArtifactLoader | None = None,
                 bindings: Phase15Bindings | Callable[[], Phase15Bindings] | None = None):
        self._settings = settings
        self._loader = loader or ArtifactLoader()
        self._bindings_source = bindings or default_bindings
        self._lock = threading.RLock()
        self._state: _State | None = None

    # ------------------------------------------------------------------------------------------- loading
    def warm_up(self) -> None:
        self._ensure_loaded()

    def _ensure_loaded(self) -> _State:
        with self._lock:
            if self._state is None:
                self._state = self._load()
            return self._state

    def _attempt(self, state: _State, name: str, fn: Callable[[], Any]) -> Any:
        try:
            result = fn()
        except Exception as exc:  # noqa: BLE001 - reported through readiness; details stay in the server log
            logger.warning("Capability '%s' could not be loaded (%s)", name, type(exc).__name__, exc_info=exc)
            state.add(name, False, _describe(exc))
            return None
        state.add(name, True)
        return result

    def _load(self) -> _State:
        s, cfg = _State(), self._settings
        try:
            b = self._bindings_source if isinstance(self._bindings_source, Phase15Bindings) \
                else self._bindings_source()
        except Exception as exc:  # noqa: BLE001 - e.g. ImportError when the ml package is not on the path
            logger.warning("Phase 1-5 bindings unavailable (%s)", type(exc).__name__, exc_info=exc)
            s.add(CAP_MODULES, False, _describe(exc))
            return s
        s.bindings, s.modules_ok = b, True
        s.add(CAP_MODULES, True)

        # --- Phase 2 model (pinned SHA-256, then Phase 3's verified loader re-checks it against its sidecar)
        s.specs[CAP_MODEL] = ArtifactSpec(CAP_MODEL, cfg.resolve(cfg.phase2_model_path), cfg.phase2_expected_sha256)
        churn = self._attempt(s, CAP_MODEL, lambda: self._loader.load_once(
            s.specs[CAP_MODEL], lambda path: b.load_churn_artifact(path, cfg.phase2_expected_sha256)))
        s.components[CAP_MODEL] = churn
        if churn is not None:
            expected = set(churn.artifact.metadata["feature_names"])
            got = set(CustomerFeatures.model_fields)
            s.schema_ok = expected == got
            s.add(CAP_SCHEMA, s.schema_ok, "ok" if s.schema_ok else "request_schema_differs_from_model_features")
            s.details.update(phase2_sha256=churn.sha256, model_version=str(churn.artifact.metadata["model_version"]),
                             decision_threshold=float(churn.artifact.threshold),
                             phase2_sha256_pinned=cfg.phase2_expected_sha256 is not None)

        # --- Phase 4 business engine (needs the model's threshold)
        s.business_cfg = self._attempt(s, "business_config", b.load_business_config)
        if s.business_cfg is not None and churn is not None:
            s.components[CAP_BUSINESS] = self._attempt(
                s, CAP_BUSINESS, lambda: b.make_business_engine(s.business_cfg, float(churn.artifact.threshold)))
        else:
            s.add(CAP_BUSINESS, False, "requires_model_and_business_config")

        # --- Phase 3 SHAP explainer (needs the raw TRAIN csv to rebuild the background)
        if churn is not None:
            def build() -> Any:
                csv = cfg.resolve(cfg.dataset_csv_path)
                if not csv.is_file():
                    raise FileNotFoundError("dataset csv")
                return b.build_explainer(churn, csv, b.load_dataset_spec(cfg.resolve(cfg.dataset_spec_path)))
            s.components[CAP_EXPLAIN] = self._attempt(s, CAP_EXPLAIN, build)
        else:
            s.add(CAP_EXPLAIN, False, "requires_model")

        # --- Phase 5 segmentation (locked K / seed / features are checked, never refit)
        s.specs[CAP_SEGMENT] = ArtifactSpec(CAP_SEGMENT, cfg.resolve(cfg.phase5_model_path), cfg.phase5_expected_sha256)
        seg = self._attempt(s, CAP_SEGMENT, lambda: self._loader.load_once(
            s.specs[CAP_SEGMENT], lambda path: b.load_segmentation_artifact(path, cfg.phase5_expected_sha256)))
        if seg is not None:
            problem = self._segmentation_mismatch(seg.metadata)
            if problem:
                s.checks[-1] = CheckResult(CAP_SEGMENT, False, problem)
                seg = None
            else:
                s.details.update(phase5_sha256=seg.sha256, segmentation_k=int(seg.metadata["selected_k"]),
                                 segmentation_version=str(seg.metadata["model_version"]))
        s.components[CAP_SEGMENT] = seg
        return s

    def _segmentation_mismatch(self, meta: Mapping[str, Any]) -> str | None:
        cfg = self._settings
        if cfg.expected_segmentation_k is not None and meta.get("selected_k") != cfg.expected_segmentation_k:
            return "segmentation_k_differs_from_locked"
        if cfg.expected_segmentation_seed is not None and meta.get("random_state") != cfg.expected_segmentation_seed:
            return "segmentation_seed_differs_from_locked"
        if cfg.expected_segmentation_features is not None \
                and tuple(meta.get("feature_names", ())) != cfg.expected_segmentation_features:
            return "segmentation_features_differ_from_locked"
        return None

    # ----------------------------------------------------------------------------------------- readiness
    def readiness(self) -> ReadinessReport:
        s = self._ensure_loaded()
        checks = list(s.checks)
        for i, check in enumerate(checks):          # re-verify the artifact bytes on disk (cheap: cached by mtime+size)
            spec = s.specs.get(check.name)
            if check.ok and spec is not None:
                status = self._loader.verify(spec)
                if not status.verified:
                    checks[i] = CheckResult(check.name, False, f"artifact_{status.reason}")
        return ReadinessReport(tuple(checks), dict(s.details))

    def _require(self, *capabilities: str) -> _State:
        s = self._ensure_loaded()
        if not s.modules_ok:
            raise integration_not_configured()
        for cap in capabilities:
            usable = s.components.get(cap) is not None and (cap != CAP_MODEL or s.schema_ok)
            if not usable:
                raise capability_unavailable(cap)
        return s

    @contextmanager
    def _translated(self, s: _State) -> Iterator[None]:
        try:
            yield
        except ApiError:
            raise
        except Exception as exc:
            mapped = s.bindings.translate_error(exc) if s.bindings else None
            if mapped is not None:
                logger.warning("Domain error translated (%s)", type(exc).__name__, exc_info=exc)
                raise mapped from exc
            raise

    # ----------------------------------------------------------------------------------------- operations
    def predict(self, customer: Mapping[str, Any]) -> PredictionResult:
        s = self._require(CAP_MODEL, CAP_BUSINESS)
        with self._translated(s):
            art = s.components[CAP_MODEL].artifact
            p = float(art.predict_proba(_to_frame(customer))[0])
            return PredictionResult(
                churn_probability=p, predicted_churn=p >= float(art.threshold), decision_threshold=float(art.threshold),
                risk_band=str(s.bindings.assign_risk_band(p, s.business_cfg)),
                model_name=str(art.metadata["model_name"]), model_version=str(art.metadata["model_version"]))

    def explain(self, customer: Mapping[str, Any]) -> ExplanationResult:
        s = self._require(CAP_MODEL, CAP_EXPLAIN)
        with self._translated(s):
            e = s.components[CAP_EXPLAIN].explain(_to_frame(customer)).to_dict()
            version = str(s.components[CAP_MODEL].artifact.metadata["model_version"])
            return ExplanationResult(
                prediction_probability=float(e["prediction_probability"]), predicted_class=int(e["predicted_class"]),
                threshold=float(e["threshold"]), base_value=float(e["base_value"]), output_space=str(e["output_space"]),
                model_log_odds=float(e["model_log_odds"]), reconstruction_error=float(e["reconstruction_error"]),
                features=[FeatureContribution(f["source_feature"], f["raw_value"], float(f["shap_value"]),
                                              f["direction"], bool(f["is_engineered"])) for f in e["features"]],
                interpretation=str(e["interpretation"]), model_version=version)

    def business(self, customer: Mapping[str, Any], churn_probability: float | None = None,
                 explanation: ExplanationResult | None = None) -> BusinessResult:
        s = self._require(CAP_MODEL, CAP_BUSINESS)
        with self._translated(s):
            if churn_probability is None:     # the business layer consumes the locked model's probability
                churn_probability = float(s.components[CAP_MODEL].artifact.predict_proba(_to_frame(customer))[0])
            engine = s.components[CAP_BUSINESS]
            profile = engine.profile(churn_probability, dict(customer), None)
            d = profile.to_dict()
            text = engine.explain(profile, explanation).to_dict()
            return BusinessResult(
                churn_probability=float(d["churn_probability"]), risk_band=str(d["risk_band"]),
                currency=str(d["currency"]), clv=float(d["clv"]), value_at_risk=float(d["value_at_risk"]),
                intervention_decision=str(d["intervention_decision"]),
                recommended_action_id=str(d["recommended_action_id"]), recommended_action=str(d["recommended_action"]),
                action_cost=float(d["action_cost"]), action_success_rate=float(d["action_success_rate"]),
                expected_benefit=float(d["expected_benefit"]), expected_cost=float(d["expected_cost"]),
                expected_net_benefit=float(d["expected_net_benefit"]),
                decision_reasons=[DecisionReason(r["code"], dict(r["values"])) for r in d["decision_reasons"]],
                decision_reason_messages=[str(m) for m in d["decision_reason_messages"]],
                action_evaluations=[ActionEvaluation(
                    a["action_id"], a["name"], float(a["cost"]), float(a["success_rate"]), bool(a["eligible"]),
                    a["ineligible_reason"], float(a["expected_benefit"]), float(a["expected_cost"]),
                    float(a["expected_net_benefit"])) for a in d["action_evaluations"]],
                explanation=BusinessExplanation(text["MODEL EXPLANATION"], text["BUSINESS DECISION"],
                                                text["disclaimer"]),
                notice=str(d["notice"]))

    def segment(self, customer: Mapping[str, Any]) -> SegmentResult:
        s = self._require(CAP_SEGMENT)
        with self._translated(s):
            seg = s.components[CAP_SEGMENT]
            segment_id, name, distance = s.bindings.assign_segment(seg, _to_frame(customer))   # nearest centroid only
            meta = seg.metadata
            entry = next((c for c in meta.get("segment_catalog", []) if c.get("segment_id") == segment_id), {})
            return SegmentResult(
                segment_id=int(segment_id), segment_name=str(name), distance_to_centroid=float(distance),
                model_version=str(meta["model_version"]), segment_count=int(meta["selected_k"]),
                customer_count=entry.get("customer_count"), priority_rank=entry.get("priority_rank"),
                priority_tier=entry.get("priority_tier"), note=SEGMENT_NOTE)
