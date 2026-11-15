"""Phase 11 runtime settings (separate from the locked Phase 6 ``Settings``)."""
from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path

from app.core.config import ENV_PREFIX, Settings

DEFAULT_AUTONOMY_DB = "data/autonomy.sqlite3"            # created EMPTY on first use; never shipped
DEFAULT_AUTONOMY_CONFIG = "configs/autonomy.yaml"


@dataclass(frozen=True)
class AutonomySettings:
    database_path: str = DEFAULT_AUTONOMY_DB
    config_path: str = DEFAULT_AUTONOMY_CONFIG

    @classmethod
    def from_env(cls, env: Mapping[str, str]) -> AutonomySettings:
        kwargs: dict[str, str] = {}
        if env.get(ENV_PREFIX + "AUTONOMY_DB") is not None:
            kwargs["database_path"] = env[ENV_PREFIX + "AUTONOMY_DB"]
        if env.get(ENV_PREFIX + "AUTONOMY_CONFIG") is not None:
            kwargs["config_path"] = env[ENV_PREFIX + "AUTONOMY_CONFIG"]
        return cls(**kwargs)

    def resolve_database(self, settings: Settings) -> str:
        return self.database_path if self.database_path == ":memory:" else str(settings.resolve(self.database_path))

    def resolve_config(self, settings: Settings) -> Path:
        return settings.resolve(self.config_path)
