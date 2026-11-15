"""Phase 9 runtime settings (kept separate from the locked Phase 6 ``Settings``)."""
from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path

from app.core.config import ENV_PREFIX, Settings

DEFAULT_RETENTION_DB = "data/campaigns.sqlite3"      # created EMPTY on first use; never shipped, never seeded
DEFAULT_RETENTION_CONFIG = "configs/retention.yaml"


@dataclass(frozen=True)
class RetentionSettings:
    database_path: str = DEFAULT_RETENTION_DB
    config_path: str = DEFAULT_RETENTION_CONFIG

    @classmethod
    def from_env(cls, env: Mapping[str, str]) -> RetentionSettings:
        kwargs: dict[str, str] = {}
        if env.get(ENV_PREFIX + "RETENTION_DB") is not None:
            kwargs["database_path"] = env[ENV_PREFIX + "RETENTION_DB"]
        if env.get(ENV_PREFIX + "RETENTION_CONFIG") is not None:
            kwargs["config_path"] = env[ENV_PREFIX + "RETENTION_CONFIG"]
        return cls(**kwargs)

    def resolve_database(self, settings: Settings) -> str:
        """``':memory:'`` is kept; other paths are anchored at the project root like every other path."""
        return self.database_path if self.database_path == ":memory:" else str(settings.resolve(self.database_path))

    def resolve_config(self, settings: Settings) -> Path:
        return settings.resolve(self.config_path)
