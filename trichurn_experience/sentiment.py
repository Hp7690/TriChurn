"""Sentiment intelligence FOUNDATION: interfaces and formats only.

Phase 13 trains no sentiment model, ships no pre-trained weights and scores no customer. The Telco dataset has no
feedback text, so ``sentiment_readiness`` returns BLOCKED_BY_MISSING_DATA until a real, labelled feedback dataset is
configured AND a model implementing ``SentimentModel`` is registered in code. Models are never loaded from files named
in configuration (pickle/joblib loading would execute arbitrary code).
"""

from __future__ import annotations

import math
import re
import unicodedata
from collections.abc import Sequence
from dataclasses import dataclass, field
from typing import Any, Protocol, runtime_checkable

from trichurn_experience.config import SentimentConfig
from trichurn_experience.schemas import BlockedByMissingData, ModuleStatus


# ------------------------------------------------------------------------------------------------ text normalization
@runtime_checkable
class TextNormalizer(Protocol):
    def normalize(self, text: str) -> str: ...


@dataclass(frozen=True)
class DefaultTextNormalizer:
    """Unicode NFKC, control characters removed, whitespace collapsed, optional lower-casing and truncation."""

    lowercase: bool = True
    max_chars: int = 5000

    def normalize(self, text: str) -> str:
        if not isinstance(text, str):
            raise TypeError("text must be a string")
        cleaned = unicodedata.normalize("NFKC", text)
        cleaned = "".join(ch for ch in cleaned if ch in "\t\n\r " or unicodedata.category(ch)[0] != "C")
        cleaned = re.sub(r"\s+", " ", cleaned).strip()
        if self.lowercase:
            cleaned = cleaned.lower()
        return cleaned[: self.max_chars]


# ------------------------------------------------------------------------------------------------ prediction schema
@dataclass(frozen=True)
class SentimentPrediction:
    feedback_id: str
    label: str
    confidence: float  # probability of `label`, in [0, 1]
    scores: dict[str, float] = field(default_factory=dict)  # optional full distribution; must sum to ~1

    def __post_init__(self) -> None:
        if not self.feedback_id or not self.label:
            raise ValueError("feedback_id and label are required.")
        if not (
            isinstance(self.confidence, (int, float)) and math.isfinite(self.confidence) and 0 <= self.confidence <= 1
        ):
            raise ValueError("confidence must be a finite number in [0, 1].")
        if self.scores:
            if (
                any(not math.isfinite(v) or v < 0 for v in self.scores.values())
                or abs(sum(self.scores.values()) - 1) > 1e-6
            ):
                raise ValueError("scores must be non-negative and sum to 1.")
            if self.label not in self.scores:
                raise ValueError("label must be a key of scores.")


@dataclass(frozen=True)
class SentimentModelMetadata:
    """What every registered model must declare. Evaluation results come from a held-out set, not the training set."""

    name: str
    version: str
    trained_at: str  # ISO 8601
    labels: tuple[str, ...]
    training_dataset_sha256: str
    training_records: int
    evaluation: SentimentEvaluationReport | None = None

    def validate(self) -> None:
        if not all((self.name, self.version, self.trained_at, self.training_dataset_sha256)):
            raise ValueError("Model metadata is incomplete.")
        if len(self.labels) < 2 or len(set(self.labels)) != len(self.labels):
            raise ValueError("A sentiment model needs at least two unique labels.")
        if self.training_records <= 0:
            raise ValueError("training_records must be positive.")
        if not re.fullmatch(r"[0-9a-f]{64}", self.training_dataset_sha256):
            raise ValueError("training_dataset_sha256 must be a 64-character lowercase hex digest.")


@runtime_checkable
class SentimentModel(Protocol):
    metadata: SentimentModelMetadata

    def predict(self, feedback_ids: Sequence[str], texts: Sequence[str]) -> list[SentimentPrediction]: ...


# ------------------------------------------------------------------------------------------------ evaluation format
@dataclass(frozen=True)
class SentimentEvaluationReport:
    """Evaluation of predictions against human labels on records the model never trained on."""

    labels: tuple[str, ...]
    n_evaluated: int
    accuracy: float
    macro_f1: float
    per_class: dict[str, dict[str, float | int]]
    confusion_matrix: list[list[int]]  # rows = true label, columns = predicted label, in `labels` order
    evaluation_dataset_sha256: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "labels": list(self.labels),
            "n_evaluated": self.n_evaluated,
            "accuracy": self.accuracy,
            "macro_f1": self.macro_f1,
            "per_class": self.per_class,
            "confusion_matrix": self.confusion_matrix,
            "evaluation_dataset_sha256": self.evaluation_dataset_sha256,
        }


def evaluate_predictions(
    y_true: Sequence[str], y_pred: Sequence[str], labels: Sequence[str], *, evaluation_dataset_sha256: str | None = None
) -> SentimentEvaluationReport:
    """Compute accuracy, per-class precision/recall/F1 and the confusion matrix from real labels and predictions."""
    if len(y_true) != len(y_pred):
        raise ValueError("y_true and y_pred must have the same length.")
    if not y_true:
        raise BlockedByMissingData("sentiment", "There are no labelled records to evaluate on.")
    labels = tuple(labels)
    index = {lab: i for i, lab in enumerate(labels)}
    if any(t not in index or p not in index for t, p in zip(y_true, y_pred, strict=True)):
        raise ValueError("Every label in y_true and y_pred must belong to `labels`.")
    k = len(labels)
    matrix = [[0] * k for _ in range(k)]
    for t, p in zip(y_true, y_pred, strict=True):
        matrix[index[t]][index[p]] += 1
    per_class: dict[str, dict[str, float | int]] = {}
    f1s: list[float] = []
    for lab, i in index.items():
        tp = matrix[i][i]
        fp = sum(matrix[r][i] for r in range(k)) - tp
        fn = sum(matrix[i]) - tp
        precision = tp / (tp + fp) if tp + fp else 0.0
        recall = tp / (tp + fn) if tp + fn else 0.0
        f1 = 2 * precision * recall / (precision + recall) if precision + recall else 0.0
        per_class[lab] = {
            "precision": round(precision, 4),
            "recall": round(recall, 4),
            "f1": round(f1, 4),
            "support": sum(matrix[i]),
        }
        f1s.append(f1)
    n = len(y_true)
    return SentimentEvaluationReport(
        labels,
        n,
        round(sum(matrix[i][i] for i in range(k)) / n, 4),
        round(sum(f1s) / k, 4),
        per_class,
        matrix,
        evaluation_dataset_sha256,
    )


# ------------------------------------------------------------------------------------------------ readiness / guard
def sentiment_readiness(
    *, feedback_valid_records: int, labelled_records: int, cfg: SentimentConfig, model: SentimentModel | None
) -> tuple[ModuleStatus, str]:
    """Status of sentiment analytics. Never AVAILABLE without real feedback AND a registered model."""
    if feedback_valid_records <= 0:
        return ModuleStatus.BLOCKED_BY_MISSING_DATA, (
            "No validated customer feedback dataset is configured. The Telco "
            "dataset contains no feedback text, so no sentiment can be derived."
        )
    if model is None:
        if labelled_records >= cfg.min_labelled_records:
            return ModuleStatus.PARTIALLY_AVAILABLE, (
                "Feedback data and enough human labels exist, but no sentiment model "
                "is registered. Training is outside Phase 13."
            )
        return ModuleStatus.PARTIALLY_AVAILABLE, (
            f"Feedback data exists but only {labelled_records} labelled records "
            f"(minimum {cfg.min_labelled_records}) and no model is registered."
        )
    return ModuleStatus.AVAILABLE, "Feedback data and a registered, documented model are available."


def predict_texts(
    model: SentimentModel | None, normalizer: TextNormalizer, feedback_ids: Sequence[str], texts: Sequence[str]
) -> list[SentimentPrediction]:
    """Run a registered model on real feedback text. Refuses without a model; refuses structured (non-text) input."""
    if model is None:
        raise BlockedByMissingData("sentiment", "No sentiment model is registered.")
    if len(feedback_ids) != len(texts):
        raise ValueError("feedback_ids and texts must have the same length.")
    if any(not isinstance(t, str) for t in texts):
        raise TypeError("Sentiment models accept feedback text only.")
    model.metadata.validate()
    return model.predict(list(feedback_ids), [normalizer.normalize(t) for t in texts])
