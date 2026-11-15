"""TriChurn Phase 6 - FastAPI layer over the locked Phase 1-5 implementation.

Dependency direction:  frontend -> app.api (routes) -> app.services -> app.services.adapters -> ml (Phase 1-5).
Only ``app/services/adapters/phase15_adapter.py`` may import the ``ml`` package.
"""

__version__ = "6.0.0"
