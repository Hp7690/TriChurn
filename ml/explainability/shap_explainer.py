"""Phase 3 - SHAP explanations for the LOCKED Phase 2 Logistic Regression artifact.

Explainer      ``shap.LinearExplainer`` (interventional, ``Independent`` masker). The locked model is a plain
               LogisticRegression; Tree/Kernel explainers are not used.
Model input    the fitted pipeline minus its last step: coerce -> engineer -> impute/scale/one-hot (dense, 58 columns
               on Telco). SHAP is computed on that transformed matrix, so it is exact for the model's linear part.
Output space   LOG-ODDS (raw margin): ``base_value + sum(shap) == decision_function(x)`` exactly (checked on every
               call against ``reconstruction.tolerance``); ``probability = sigmoid(log_odds)``.
Background     up to ``background.max_rows`` RAW rows sampled with a fixed seed from the TRAIN split only, feature
               columns only (no target, no validation/test rows). ``base_value`` is the mean log-odds over it.
Calibration    only ``none`` is supported: then the model probability is exactly sigmoid(log-odds). A Platt or
               isotonic calibrator would make log-odds SHAP differ from the reported probability, so it is refused.
Reporting      encoded columns are summed back to source features (see ``feature_importance``).

Artifact integrity: ``load_verified_artifact`` hashes the artifact BYTES, compares with the SHA-256 in the trusted
metadata sidecar and only then deserialises those same bytes (no re-read, so no check/use gap). The Phase 2 loader
``serialization.load_artifact`` does not verify hashes; it is left unchanged.
"""
from __future__ import annotations

import hashlib
import io
import json
import math
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import joblib
import numpy as np
import pandas as pd
import shap
from scipy.special import expit
from sklearn.linear_model import LogisticRegression

from ml.config import load_config
from ml.errors import (
    ArtifactIntegrityError,
    ExplainabilityError,
    ExplainabilityInputError,
)
from ml.explainability.feature_importance import (
    FeatureMap,
    build_feature_map,
    direction_for,
    global_importance,
    top_negative_drivers,
    top_positive_drivers,
)
from ml.explainability.schemas import (
    OUTPUT_SPACE,
    FeatureContribution,
    GlobalImportanceItem,
    LocalExplanation,
)
from ml.pipelines.calibration import CalibratedModel
from ml.pipelines.ingestion import DatasetSpec, dataset_version, load_csv
from ml.pipelines.serialization import ModelArtifact
from ml.pipelines.training import split_raw

_SHA_LEN = 64


# ================================================================================ artifact integrity
@dataclass
class VerifiedArtifact:
    artifact: ModelArtifact
    sidecar: dict          # trusted metadata (.metadata.json)
    sha256: str
    path: Path


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def default_metadata_path(model_path: Path) -> Path:
    return model_path.with_name(f"{model_path.stem}.metadata.json")


def load_verified_artifact(model_path: str | Path, metadata_path: str | Path | None = None,
                           expected_sha256: str | None = None) -> VerifiedArtifact:
    """bytes -> SHA-256 -> compare with trusted metadata -> (only then) deserialise -> cross-check metadata.

    ``expected_sha256`` pins the digest out-of-band (e.g. from a release record); otherwise the sidecar's
    ``artifact_sha256`` is used. The sidecar is only as trustworthy as where it came from: a party who can rewrite
    both files can also rewrite the digest, which is why an out-of-band digest can be supplied."""
    model_path = Path(model_path)
    meta_path = Path(metadata_path) if metadata_path else default_metadata_path(model_path)
    try:
        raw = model_path.read_bytes()
    except OSError as exc:
        raise ArtifactIntegrityError(f"Cannot read model artifact '{model_path.name}': {exc}") from exc
    try:
        sidecar = json.loads(meta_path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise ArtifactIntegrityError(f"Cannot read trusted metadata '{meta_path.name}': {exc}") from exc
    if not isinstance(sidecar, dict):
        raise ArtifactIntegrityError("Trusted metadata is not a JSON object.")

    expected = (expected_sha256 or sidecar.get("artifact_sha256") or "").strip().lower()
    if len(expected) != _SHA_LEN:
        raise ArtifactIntegrityError("No valid SHA-256 digest is available in the trusted metadata.")
    actual = sha256_bytes(raw)
    if actual != expected:
        raise ArtifactIntegrityError(
            f"Artifact SHA-256 mismatch for '{model_path.name}': expected {expected[:12]}..., computed "
            f"{actual[:12]}.... The file was modified or does not belong to this metadata; it was NOT loaded.")
    if sidecar.get("artifact_file") not in (None, model_path.name):
        raise ArtifactIntegrityError(
            f"Metadata describes '{sidecar.get('artifact_file')}', not '{model_path.name}'.")

    try:
        bundle = joblib.load(io.BytesIO(raw))      # the verified bytes themselves
        artifact = ModelArtifact(bundle)
    except Exception as exc:  # noqa: BLE001 - any failure to restore a verified file is an artifact problem
        raise ArtifactIntegrityError(f"The verified artifact could not be restored: {exc}") from exc

    embedded = artifact.metadata
    checks = {
        "model_name": (embedded.get("model_name"), sidecar.get("model_name")),
        "feature_names": (embedded.get("feature_names"), sidecar.get("feature_names")),
        "model_feature_names": (embedded.get("model_feature_names"), sidecar.get("model_feature_names")),
        "calibration method": ((embedded.get("calibration") or {}).get("method"),
                               (sidecar.get("calibration") or {}).get("method")),
        "threshold": (artifact.threshold, (sidecar.get("threshold") or {}).get("value")),
    }
    for what, (a, b) in checks.items():
        if a != b:
            raise ArtifactIntegrityError(f"Artifact and trusted metadata disagree on {what}: {a!r} vs {b!r}.")
    return VerifiedArtifact(artifact, sidecar, actual, model_path)


# ======================================================================================= input validation
def _is_blank(v: Any) -> bool:
    if v is None:
        return True
    if isinstance(v, str):
        return v.strip() == ""
    try:
        return bool(pd.isna(v))
    except (TypeError, ValueError):
        return False


def _bad(msg: str) -> ExplainabilityInputError:
    return ExplainabilityInputError(msg)


def validate_input(X: Any, features: list[str], numeric: list[str], categorical: list[str]) -> pd.DataFrame:
    """Raw customer record(s) -> DataFrame with exactly the model's raw columns, in order.

    Accepts a DataFrame, one record (Mapping) or a list of records. Rejects: empty input, wrong container,
    duplicate columns, missing required columns, non-scalar cells, booleans or non-numeric text in numeric
    columns, and +/-inf. Blank/null cells are allowed (the pipeline imputes them; ``raw_value`` is then None).
    Columns beyond the required ones are ignored. Unknown category values are allowed (all-zero one-hot)."""
    if isinstance(X, pd.DataFrame):
        df = X
    elif isinstance(X, Mapping):
        df = pd.DataFrame([dict(X)])
    elif isinstance(X, (list, tuple)) and X and all(isinstance(r, Mapping) for r in X):
        df = pd.DataFrame([dict(r) for r in X])
    elif isinstance(X, (list, tuple)) and not X:
        raise _bad("Input is empty: provide at least one customer record.")
    else:
        raise _bad("Input must be a pandas DataFrame, a record (dict) or a list of records (dicts).")
    if len(df) == 0:
        raise _bad("Input is empty: provide at least one customer record.")
    if df.columns.duplicated().any():
        raise _bad(f"Duplicate columns in input: {sorted(set(df.columns[df.columns.duplicated()].astype(str)))}.")
    missing = [c for c in features if c not in df.columns]
    if missing:
        raise _bad(f"Missing required feature(s): {missing}.")
    df = df[features].reset_index(drop=True).copy()

    for col in features:
        s = df[col]
        blank = s.map(_is_blank)
        for i, v in s[~blank].items():
            if isinstance(v, (list, tuple, set, dict, np.ndarray)):
                raise _bad(f"Row {i}, '{col}': value must be a single scalar, got {type(v).__name__}.")
            if col in numeric:
                if isinstance(v, (bool, np.bool_)):
                    raise _bad(f"Row {i}, '{col}': numeric feature received a boolean.")
                try:
                    f = float(str(v).strip()) if isinstance(v, str) else float(v)
                except (TypeError, ValueError):
                    raise _bad(f"Row {i}, '{col}': {v!r} is not a valid number.") from None
                if not math.isfinite(f):
                    raise _bad(f"Row {i}, '{col}': value must be finite, got {v!r}.")
    return df


# ===================================================================================== TRAIN background
def select_background(train_raw: pd.DataFrame, features: list[str], max_rows: int, seed: int,
                      target: str | None = None) -> pd.DataFrame:
    """Deterministic, bounded sample of TRAIN rows, feature columns only (the target can never be included)."""
    if target is not None and target in features:
        raise ExplainabilityError("The target column cannot be a model feature / background column.")
    if not isinstance(max_rows, int) or max_rows < 1:
        raise ExplainabilityError("background.max_rows must be a positive integer.")
    missing = [c for c in features if c not in train_raw.columns]
    if missing:
        raise ExplainabilityError(f"Background data lacks required feature(s): {missing}.")
    if len(train_raw) == 0:
        raise ExplainabilityError("Background data is empty.")
    frame = train_raw[features]
    return frame.sample(n=min(max_rows, len(frame)), random_state=seed)   # keeps original index (provenance)


def load_train_background(csv_path: str | Path, spec: DatasetSpec, verified: VerifiedArtifact,
                          config: dict | None = None) -> pd.DataFrame:
    """Rebuild the Phase 2 TRAIN split from the original CSV and sample the background from it.

    Uses the split settings and seed stored in the artifact metadata, and refuses to continue unless the dataset
    version and TRAIN size match what Phase 2 recorded (so validation/test rows can never leak in)."""
    cfg = config or load_config("explainability")
    meta = verified.artifact.metadata
    csv_path = Path(csv_path)
    ds = meta.get("dataset") or {}
    version = dataset_version(csv_path)
    if ds.get("version") and ds["version"] != version:
        raise ExplainabilityError(f"Dataset version {version} differs from the one the model was trained on "
                                  f"({ds['version']}); cannot reproduce the TRAIN split.")
    tcfg = ((meta.get("training_configuration") or {}).get("training")) or {}
    split = tcfg.get("split") or {}
    seed = meta.get("random_state", tcfg.get("seed"))
    if "val_size" not in split or "test_size" not in split or seed is None:
        raise ExplainabilityError("Artifact metadata lacks the split configuration needed to rebuild TRAIN.")
    parts = split_raw(load_csv(csv_path), spec, split["val_size"], split["test_size"], int(seed))
    expected_train = (ds.get("split_sizes") or {}).get("train")
    if expected_train is not None and len(parts.train) != expected_train:
        raise ExplainabilityError(f"Rebuilt TRAIN has {len(parts.train)} rows; Phase 2 recorded {expected_train}.")
    return select_background(parts.train, meta["feature_names"], cfg["background"]["max_rows"], cfg["seed"],
                             target=meta.get("target"))


# ========================================================================================== the explainer
def _py(v: Any) -> Any:
    """JSON-friendly scalar: NaN/None -> None, numpy scalars -> Python."""
    if v is None or (isinstance(v, float) and math.isnan(v)):
        return None
    if isinstance(v, np.generic):
        v = v.item()
        return None if isinstance(v, float) and math.isnan(v) else v
    try:
        if pd.isna(v):
            return None
    except (TypeError, ValueError):
        pass
    return v


class ChurnShapExplainer:
    """SHAP explanations (log-odds, source-feature level) for the locked Logistic Regression."""

    explainer_type = "shap.LinearExplainer (interventional, Independent masker)"
    output_space = OUTPUT_SPACE

    def __init__(self, verified: VerifiedArtifact, background_raw: pd.DataFrame, config: dict | None = None):
        cfg = config or load_config("explainability")
        self.config = cfg
        self.tolerance = float(cfg["reconstruction"]["tolerance"])
        self.epsilon = float(cfg["direction_epsilon"])
        self.artifact = verified.artifact
        self.sha256 = verified.sha256
        model = self.artifact.model
        if not isinstance(model, CalibratedModel) or model.method != "none":
            raise ExplainabilityError(
                "Only an uncalibrated model (calibration = none) is supported: with Platt/isotonic calibration the "
                "log-odds SHAP values would not add up to the reported probability.")
        self.base_pipeline = model.base
        estimator = self.base_pipeline.named_steps["model"]
        if not isinstance(estimator, LogisticRegression):
            raise ExplainabilityError(f"Expected a LogisticRegression, found {type(estimator).__name__}.")
        if estimator.coef_.shape[0] != 1:
            raise ExplainabilityError("Only binary Logistic Regression is supported.")
        self._lr = estimator
        self._preprocess = self.base_pipeline.named_steps["preprocess"]
        coercer = self.base_pipeline.named_steps["coerce"]
        meta = self.artifact.metadata
        self.features: list[str] = list(meta["feature_names"])
        self._numeric, self._categorical = list(coercer.numeric or []), list(coercer.categorical or [])
        self.threshold = float(self.artifact.threshold)

        self.feature_map: FeatureMap = build_feature_map(self._preprocess)
        if self.feature_map.encoded_names != list(meta["model_feature_names"]):
            raise ExplainabilityError("Preprocessor output names differ from the artifact's model_feature_names.")
        if len(self.feature_map.encoded_names) != estimator.coef_.shape[1]:
            raise ExplainabilityError("Encoded feature count does not match the model's coefficients.")
        self.engineered = {s for s in self.feature_map.sources if s not in set(self.features)}

        bg = select_background(background_raw, self.features, int(cfg["background"]["max_rows"]),
                               int(cfg["seed"]), target=meta.get("target"))
        self.background_raw = validate_input(bg, self.features, self._numeric, self._categorical)
        self.background_index = list(bg.index)
        z_bg = self._encode(self.background_raw)[1]
        if not np.isfinite(z_bg).all():
            raise ExplainabilityError("Transformed background contains non-finite values.")
        self._explainer = shap.LinearExplainer(
            estimator, shap.maskers.Independent(z_bg, max_samples=len(z_bg)))
        self.base_value = float(np.ravel(self._explainer.expected_value)[0])

    # ---------------------------------------------------------------------------------------- internals
    def _encode(self, raw: pd.DataFrame) -> tuple[pd.DataFrame, np.ndarray]:
        engineered = self.base_pipeline[:2].transform(raw)            # coerce -> feature engineering
        z = self._preprocess.transform(engineered)                    # impute / scale / one-hot
        z = z.toarray() if hasattr(z, "toarray") else np.asarray(z, dtype=float)
        return engineered, z

    def _compute(self, X: Any) -> tuple[pd.DataFrame, pd.DataFrame, np.ndarray, np.ndarray, np.ndarray]:
        raw = validate_input(X, self.features, self._numeric, self._categorical)
        engineered, z = self._encode(raw)
        if not np.isfinite(z).all():
            raise ExplainabilityInputError("Input could not be encoded into finite model features.")
        sv = self._explainer.shap_values(z)
        if isinstance(sv, list):
            raise ExplainabilityError("Unexpected multi-output SHAP result for a binary linear model.")
        sv = np.asarray(sv, dtype=float)
        if sv.shape != z.shape:
            raise ExplainabilityError(f"SHAP values have shape {sv.shape}, expected {z.shape}.")
        log_odds = self._lr.decision_function(z)
        err = np.abs(self.base_value + sv.sum(axis=1) - log_odds)
        if err.max() > self.tolerance:
            raise ExplainabilityError(
                f"SHAP reconstruction failed: max |base + sum(SHAP) - log-odds| = {err.max():.3e} "
                f"> tolerance {self.tolerance:g}.")
        prob = self.artifact.predict_proba(raw)
        if np.abs(expit(log_odds) - prob).max() > self.tolerance:
            raise ExplainabilityError("sigmoid(log-odds) does not match the model's probability.")
        return raw, engineered, sv, log_odds, prob

    def _explanations(self, X: Any) -> list[LocalExplanation]:
        _, engineered, sv, log_odds, prob = self._compute(X)
        agg = self.feature_map.aggregate(sv)
        out = []
        for i in range(len(prob)):
            feats = [FeatureContribution(
                source_feature=s, raw_value=_py(engineered.iloc[i][s]), shap_value=float(agg[i, j]),
                direction=direction_for(float(agg[i, j]), self.epsilon), is_engineered=s in self.engineered)
                for j, s in enumerate(self.feature_map.sources)]
            feats.sort(key=lambda f: (-round(abs(f.shap_value), 12), f.source_feature))
            total = self.base_value + float(sum(f.shap_value for f in feats))
            out.append(LocalExplanation(
                prediction_probability=float(prob[i]), predicted_class=int(prob[i] >= self.threshold),
                threshold=self.threshold, base_value=self.base_value, output_space=self.output_space,
                features=feats, model_log_odds=float(log_odds[i]),
                reconstruction_error=abs(total - float(log_odds[i]))))
        return out

    # -------------------------------------------------------------------------------------------- public
    def explain(self, record: Any) -> LocalExplanation:
        """Explain ONE customer (a dict or a one-row DataFrame of raw fields)."""
        result = self._explanations(record)
        if len(result) != 1:
            raise ExplainabilityInputError(f"explain() takes exactly one record, got {len(result)}; "
                                           "use explain_many().")
        return result[0]

    def explain_many(self, X: Any) -> list[LocalExplanation]:
        return self._explanations(X)

    def global_importance(self, X: Any) -> list[GlobalImportanceItem]:
        """mean(|SHAP|) per source feature over the rows of ``X`` (raw customer records)."""
        _, _, sv, _, _ = self._compute(X)
        return global_importance(self.feature_map, sv)

    def top_positive_drivers(self, record: Any, n: int = 5) -> list[FeatureContribution]:
        """Features that pushed THIS customer's model score up (log-odds > 0), largest first."""
        return top_positive_drivers(self.explain(record), n)

    def top_negative_drivers(self, record: Any, n: int = 5) -> list[FeatureContribution]:
        """Features that pushed THIS customer's model score down (log-odds < 0), most negative first."""
        return top_negative_drivers(self.explain(record), n)

    def describe(self) -> dict:
        return {"explainer": self.explainer_type, "output_space": self.output_space,
                "background_rows": len(self.background_raw), "background_seed": self.config["seed"],
                "background_source": "TRAIN split only, feature columns only",
                "n_encoded_features": len(self.feature_map.encoded_names),
                "n_source_features": len(self.feature_map.sources), "base_value": self.base_value,
                "threshold": self.threshold, "artifact_sha256": self.sha256,
                "reconstruction_tolerance": self.tolerance}
