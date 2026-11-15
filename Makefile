.PHONY: test lint data train optimize business segment
test:
	python -m pytest
lint:
	ruff check .
data:
	python scripts/download_telco.py
train:
	python scripts/run_phase1.py
optimize:
	python scripts/run_phase2.py
business:
	python scripts/run_phase4.py
segment:
	python scripts/run_phase5.py
