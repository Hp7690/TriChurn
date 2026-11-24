# TriChurn — AI-Powered Customer Churn & Retention Intelligence

An explainable AI-powered customer churn prediction and retention intelligence platform built with React, TypeScript, FastAPI and machine learning.

## Project Status
- Backend verification: Passed
- Frontend verification: Passed
- Deployment: https://trichurn-frontend.vercel.app/dashboard
- Project scope: Churn prediction, explainability, customer segmentation, retention and revenue intelligence.

## Technology Stack
- Frontend: React, TypeScript, Vite
- Backend: Python, FastAPI
- ML: scikit-learn, XGBoost, SHAP
- Data: Pandas, NumPy
- Tracking: MLflow
- Tests: Pytest, Vitest

## Verified Churn Model Results
- Model: Logistic Regression v2.0.0
- ROC-AUC: 0.8492
- PR-AUC: 0.6412
- Accuracy: 77.11%
- Precision: 55.03%
- Recall: 74.29%
- F1 Score: 0.6322
- Test set: 1,057 records
- Decision threshold: 0.34 (validation-selected)

## Main Modules
- Churn prediction and explainability
- Customer segmentation
- Retention intelligence and what-if analysis
- Revenue intelligence
- Model lifecycle and operational workflows

## Local Setup
1. Create and activate a Python virtual environment.
2. Install backend dependencies: `pip install -r requirements.txt`.
3. Start backend: `uvicorn app.main:app --reload`.
4. In the frontend folder, run `npm ci` and `npm run dev`.

## Verification
- Backend: Pytest
- Frontend: Vitest
- Frontend type checking and production build
- Python linting: Ruff

## Data and Model Governance
Customer datasets, local databases, environment files and binary model artifacts are excluded from Git. Simulated outputs must not be treated as observed customer outcomes.

## Deployment
Full-stack public deployment is not yet verified.

## Author
Harsh Pandey
