"""Phase 12 service: lazy, cached construction of the RevenueEngine and error translation.

Independent of Phases 9/11: it reads a CSV snapshot only. A missing file or bad configuration yields 503 on Phase 12
routes only and never affects other routes. No business arithmetic lives here.
"""
from __future__ import annotations

import logging
import os
import threading
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from revenue_intelligence.analytics.config import RevenueConfig, load_config
from revenue_intelligence.analytics.dataset import read_csv_safely, resolve_csv_path
from revenue_intelligence.analytics.engine import RevenueEngine
from revenue_intelligence.errors import (
    RevenueConfigError,
    RevenueDataUnavailableError,
    RevenueInputError,
    RevenueIntelligenceError,
)

logger = logging.getLogger("trichurn.api.revenue_intelligence")
ENV = "TRICHURN_"


@dataclass(frozen=True)
class RevenueSettings:
    project_root: str = "."
    config_path: str = "configs/revenue_intelligence.yaml"
    data_csv: str | None = None
    history_csv: str | None = None

    @classmethod
    def from_env(cls, env: Any = None) -> RevenueSettings:
        env = os.environ if env is None else env
        return cls(project_root=env.get(ENV + "PROJECT_ROOT", "."),
                   config_path=env.get(ENV + "REVENUE_CONFIG", "configs/revenue_intelligence.yaml"),
                   data_csv=env.get(ENV + "REVENUE_DATA_CSV") or None,
                   history_csv=env.get(ENV + "REVENUE_HISTORY_CSV") or None)


class ServiceError(Exception):
    def __init__(self, status: int, code: str, message: str):
        super().__init__(message)
        self.status, self.code, self.message = status, code, message


def translate(exc: Exception) -> ServiceError:
    """Domain error -> HTTP error. Messages are fixed/safe: no file paths, stack traces or customer data."""
    if isinstance(exc, ServiceError):
        return exc
    if isinstance(exc, RevenueInputError):
        return ServiceError(422, exc.code, str(exc))
    if isinstance(exc, RevenueDataUnavailableError):
        return ServiceError(503, exc.code, str(exc))
    if isinstance(exc, RevenueConfigError):
        return ServiceError(503, exc.code, "Revenue intelligence configuration is invalid.")
    if isinstance(exc, RevenueIntelligenceError):
        return ServiceError(500, exc.code, "Revenue intelligence failed.")
    return ServiceError(500, "INTERNAL_ERROR", "An unexpected error occurred.")


class RevenueIntelligenceService:
    def __init__(self, settings: RevenueSettings | None = None, engine: RevenueEngine | None = None,
                 config: RevenueConfig | None = None):
        self.settings = settings or RevenueSettings()
        self._engine, self._config = engine, config
        self._stamp: tuple | None = None
        self._lock = threading.Lock()

    def _root(self) -> Path:
        return Path(self.settings.project_root).resolve()

    def _stamp_of(self, path: Path, hist: Path | None) -> tuple:
        return (path, path.stat().st_mtime_ns, hist, hist.stat().st_mtime_ns if hist else None)

    def engine(self) -> RevenueEngine:
        with self._lock:
            if self._engine is not None and self.settings.data_csv is None and self._stamp is None:
                return self._engine                      # injected engine (tests / embedding)
            cfg = self._config or load_config(self._root() / self.settings.config_path
                                              if not Path(self.settings.config_path).is_absolute()
                                              else self.settings.config_path)
            path = resolve_csv_path(self.settings.data_csv, cfg.data.candidate_paths, self._root())
            hist = None
            if self.settings.history_csv:
                hist = resolve_csv_path(self.settings.history_csv, (), self._root())
            stamp = self._stamp_of(path, hist)
            if self._engine is None or stamp != self._stamp:
                raw = read_csv_safely(path, cfg.data)
                frame = read_csv_safely(hist, cfg.data) if hist is not None else None
                self._engine = RevenueEngine(raw, cfg, frame, source_label=f"CSV snapshot: {path.name}")
                self._stamp = stamp
                logger.info("Revenue engine built: %d customers", self._engine.quality.rows_used)
            return self._engine

    def call(self, name: str, *args: Any, **kwargs: Any) -> Any:
        try:
            return getattr(self.engine(), name)(*args, **kwargs)
        except ServiceError:
            raise
        except RevenueIntelligenceError as exc:
            raise translate(exc) from exc
        except Exception as exc:    # noqa: BLE001
            logger.error("Revenue intelligence failure (%s)", type(exc).__name__)
            raise translate(exc) from exc


def build_revenue_service(settings: RevenueSettings | None = None) -> RevenueIntelligenceService:
    return RevenueIntelligenceService(settings or RevenueSettings.from_env())
