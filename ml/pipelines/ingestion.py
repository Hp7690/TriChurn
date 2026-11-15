"""Dataset ingestion: safe CSV loading, dataset versioning and column-role suggestion."""
from __future__ import annotations

import hashlib
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, BinaryIO

import pandas as pd

from ml.config import load_yaml
from ml.errors import IngestionError


@dataclass
class DatasetSpec:
    """User-selected meaning of the dataset's columns."""

    target: str
    positive_class: Any
    id_column: str | None = None
    value_column: str | None = None
    numerical: list[str] = field(default_factory=list)
    categorical: list[str] = field(default_factory=list)
    exclude: list[str] = field(default_factory=list)

    @classmethod
    def from_yaml(cls, path: str | Path) -> DatasetSpec:
        return cls(**load_yaml(path))

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def file_sha256(path: str | Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def dataset_version(path: str | Path) -> str:
    """Content-addressed dataset version (same bytes => same version)."""
    return f"sha256:{file_sha256(path)[:12]}"


def load_csv(source: str | Path | BinaryIO, max_file_mb: float = 50) -> pd.DataFrame:
    """Load a CSV with extension, size and emptiness checks."""
    if isinstance(source, (str, Path)):
        path = Path(source)
        if path.suffix.lower() != ".csv":
            raise IngestionError(f"Unsupported file type '{path.suffix}'. Please upload a .csv file.")
        if not path.exists():
            raise IngestionError(f"File not found: {path}")
        size_mb = path.stat().st_size / (1024 * 1024)
        if size_mb > max_file_mb:
            raise IngestionError(
                f"File is {size_mb:.1f} MB, above the {max_file_mb:g} MB limit."
            )
    try:
        df = pd.read_csv(source)
    except pd.errors.EmptyDataError as exc:
        raise IngestionError("The CSV file is empty.") from exc
    except (pd.errors.ParserError, UnicodeDecodeError) as exc:
        raise IngestionError(f"The file could not be parsed as CSV: {exc}") from exc
    if df.empty:
        raise IngestionError("The CSV has a header but no data rows.")
    df.columns = [str(c).strip() for c in df.columns]
    return df


_TARGET_HINTS = ("churn", "attrition", "exited", "left", "cancel")


def suggest_target_candidates(df: pd.DataFrame) -> list[str]:
    """Columns that look like a binary outcome. Suggestions only; the user decides."""
    out = []
    for col in df.columns:
        n = df[col].nunique(dropna=True)
        name_hit = any(h in col.lower() for h in _TARGET_HINTS)
        if n == 2 or (name_hit and 2 <= n <= 5):
            out.append(col)
    out.sort(key=lambda c: not any(h in c.lower() for h in _TARGET_HINTS))
    return out
