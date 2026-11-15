"""The ONLY integration boundary to the locked Phase 1-5 implementation.

* ``interface``        - the ``Phase15Port`` protocol and framework-free result DTOs (what the API needs).
* ``phase15_adapter``  - the REAL production adapter; the only module in ``app/`` allowed to import ``ml``.
* ``unavailable``      - a non-fake placeholder that answers 503 when the integration cannot be loaded.
* ``factory``          - chooses the adapter at start-up (custom factory via ``TRICHURN_ADAPTER_FACTORY``).

A TEST-ONLY fake adapter exists under ``tests/support/`` and is deliberately NOT part of this package.
"""
