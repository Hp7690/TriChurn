# TriChurn Frontend — Customer Churn Prediction & Retention Intelligence

**Live Frontend:** https://trichurn-frontend.vercel.app/dashboard

TriChurn is an AI-powered customer churn prediction and retention intelligence platform. Its frontend is built with React, TypeScript and Vite, and follows the workflow:

**Predict → Explain → Quantify → Decide → Retain**

## Technology Stack

- React + TypeScript + Vite
- Tailwind CSS
- Recharts + Lucide
- Clerk authentication integration
- FastAPI backend integration
- Vitest + ESLint

## Project Status

- Backend verification: Passed
- Frontend tests: Passed
- Type checking: Passed
- Production build: Passed
- Frontend deployment: Available on Vercel
- Full-stack public deployment: Not yet verified
- Clerk browser-to-backend authentication: Integration implemented; end-to-end verification pending

## Run Locally

From the project root:

```bash
# Backend
python -m pip install -r requirements.txt
python -m uvicorn app.main:app --reload --env-file .env
```

In another terminal:

```bash
# Frontend
cd frontend
npm ci
npm run dev
```

Frontend: `http://localhost:5173`

Backend API: `http://127.0.0.1:8000`

Health endpoint: `http://127.0.0.1:8000/api/v1/health`

## Build, Test and Lint

Run these commands from the `frontend` directory:

```bash
npm run build
npm run test
npm run lint
npm run typecheck
```

## Application Pages

| Route | Description |
|---|---|
| `/dashboard` | Executive dashboard with KPIs, risk, segment and opportunity charts |
| `/customers` | Customer search, risk filters, probability filters and pagination |
| `/customers/:customerId` | Customer overview, business value and explainability |
| `/segments` | Customer segments, charts and comparison |
| `/insights` | Value-at-risk, highest-value opportunities and action summaries |
| `/what-if` | Scenario analysis and retention decision support |
| `/model` | Model metrics and configuration (read-only) |
| `/retention/*` | Retention overview, priorities, recommendations, simulator and campaigns |
| `/autonomous/*` | Command center, risk monitor, recommendations, approvals and audit |
| `/revenue/*` | CLV, revenue at risk, upsell, cross-sell, cohorts and forecasting |
| `/experience` | Customer experience data availability |
| `/experience-lifecycle` | Tenure-based lifecycle analysis |
| `/settings` | Appearance and data-source settings |

## Authentication

The frontend integrates Clerk for user sign-in and session management.

- Clerk handles the frontend sign-in experience.
- The frontend token bridge obtains the Clerk session token.
- API adapters attach the session token as a Bearer authorization header.
- The backend validates Clerk session tokens and applies reviewer authorization.
- Protected autonomy endpoints reject unauthenticated requests.

Authentication configuration is required in the local environment. Never commit secret keys or session tokens.

## Data Sources

The core intelligence pages use `IntelligenceService`.

The default data provider is `MockDataProvider`, which supplies deterministic demonstration data. The FastAPI adapter can be selected through:

```dotenv
VITE_DATA_PROVIDER=fastapi
VITE_API_BASE_URL=http://127.0.0.1:8000
```

Copy `.env.example` to `.env` and configure the required values.

Retention, Autonomous, Revenue, Experience and Lifecycle modules use their respective HTTP providers. They do not silently substitute mock data when API data is unavailable; the UI displays the relevant unavailable, blocked or error state.

## Mock Data and Governance

The frontend includes 80 deterministic demo customers (`TC-1001` to `TC-1080`), generated from a fixed seed.

- Demo customer-level probabilities, CLV, VaR, ENB, explanations and actions are illustrative.
- Simulated outputs must not be interpreted as observed customer outcomes.
- The locked model metrics and configuration displayed on `/model` are separate from illustrative mock customer results.
- The frontend does not train models, calculate SHAP values or perform customer clustering.

Mock-only environment variables:

```dotenv
VITE_MOCK_LATENCY_MS=250
VITE_MOCK_FAIL=none
```

The Settings page also provides a developer toggle for testing API failure states.

## Design System

Light, dark and system themes are supported through the top bar and Settings page.

See [DESIGN_SYSTEM.md](DESIGN_SYSTEM.md).

## Project Structure

```text
frontend/
├── src/
│   ├── components/     Reusable UI components
│   ├── charts/         Recharts visualizations
│   ├── layouts/        Application layout
│   ├── pages/          Route-level pages
│   ├── services/
│   │   ├── api/        API contracts, auth token bridge and errors
│   │   ├── adapters/   Mock and FastAPI data providers
│   │   ├── autonomy/   Autonomy service providers
│   │   ├── retention/  Retention service providers
│   │   └── revenue/    Revenue service providers
│   ├── data/           Demo data and model information
│   ├── hooks/
│   ├── utils/
│   ├── types/
│   └── __tests__/
├── .env.example
├── package.json
└── README.md
```

## Scope and Responsibilities

The frontend is responsible for application UI, visualization, API integration, authentication flow and user interaction.

Model training, model evaluation, SHAP computation, PostgreSQL, MLflow tracking, retraining and backend orchestration belong to the backend and ML layers.

## Deployment

The frontend is deployed on Vercel:

https://trichurn-frontend.vercel.app/dashboard

The public frontend URL does not by itself establish that every backend-dependent feature is operational in production. Full-stack public deployment remains unverified.

## Author

**Harsh Pandey**  
B.Tech — Data Science & Artificial Intelligence

GitHub: [Hp7690](https://github.com/Hp7690)

**TriChurn** — An AI-powered customer churn prediction and retention intelligence project.
