# mlops - TriChurn Phase 8

MLflow tracking, Model Registry and SHA-256 integrity for the **existing** Phase 2 churn model. Full documentation:
[`docs/phase8.md`](../docs/phase8.md). Named `mlops` (not `mlflow`) so it never shadows the real library.

    python scripts/run_phase8_registry.py verify | register | status | fetch --dest DIR
