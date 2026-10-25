# Savora — FMCG Operations & Surplus Intelligence

Savora is a React/TypeScript and Flask application for inventory visibility, demand forecasting, surplus assessment, redistribution planning, recovery allocation, scenario analysis and operational outcome recording.

## Core capabilities

- React + TypeScript + Vite workspace with responsive navigation and charting.
- Login/logout, persisted sessions, protected business API routes and password hashing using PBKDF2-SHA256 (legacy local hashes are upgraded on successful login).
- SQLite persistence for users, company profile, products, locations, recovery partners, inventory batches and sales history.
- Create, update and delete API operations where supported, with relationship safeguards for products and locations.
- Dashboard metrics and charts based on saved inventory/sales records.
- Demand forecast API using a persisted trained scikit-learn model when it is current and wins against the historical-average baseline; otherwise it uses the baseline.
- Chronological holdout evaluation for historical-average, Random Forest and Histogram Gradient Boosting models.
- Explicit model retraining endpoint that saves model artifacts and the training sales-record count. A change in sales count marks the saved model stale; retrain to update it.
- Surplus calculations, constraint-aware redistribution heuristic, recovery allocation, discount scenarios, and what-if simulation.
- Product/location/partner management, company profile and system settings.
- API tests and business-rule tests.

## Requirements

- Python 3.10+
- Node.js 20+
- SQLite (included with Python)

## Windows setup

### Backend (PowerShell)

```powershell
cd savora\backend
py -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
Copy-Item .env.example .env
python run.py
```

Backend health: `http://127.0.0.1:5000/health`

### Frontend (second terminal)

```powershell
cd savora\frontend
Copy-Item .env.example .env
npm install
npm run dev
```

Open the local URL printed by Vite. The backend CORS configuration permits localhost ports 5173 and 5174 by default.

## Initial local administrator

On a new database, the initial account is configured by `ADMIN_EMAIL` and `ADMIN_PASSWORD` in `backend/.env`. Defaults for local setup:

- Email: `admin@savora.local`
- Password: `ChangeMe123!`

Change these values before the first database initialization. If a database already exists, changing environment values does not reset an existing account password. Do not use the defaults for a shared or public deployment.

## Database and initial dataset

The application initializes `backend/savora.sqlite3` on first start and seeds initial operational records when the corresponding tables are empty, so the workspace can be explored without importing a company dataset. These initial records are fictional seed records, not real company transactions. Replace or supplement them with verified operational records before relying on business decisions. Product, location, partner, company profile, inventory and sales records persist in SQLite.

To preserve data, back up `backend/savora.sqlite3` before upgrades or manual edits.

## Forecast model workflow

1. Start the backend and sign in.
2. Add or import eligible historical sales records through the sales API or your integration.
3. Open **Model Performance** and run **Train model**.
4. Review chronological holdout MAE/RMSE and the selected baseline/model.
5. Generate forecasts from **Demand Forecasting**.

Training uses chronological evaluation. The selected trained estimator is persisted in `backend/app/trained_model.joblib`. The artifact stores the training sales-record count; adding sales records makes it stale, and the forecast endpoint falls back to the historical average until retraining. The trained estimator is deployed for forecasting only when the historical evaluation indicates it beats the historical-average baseline. This is a deliberate safeguard, not a claim that training always improves forecasts.

## Testing

Backend:

```powershell
cd savora\backend
python -m pytest -q
```

Frontend production build:

```powershell
cd savora\frontend
npm install
npm run build
```

## Important operational boundaries

- SQLite is the active runtime database. `database/schema.sql` is a separate MySQL reference schema; the runtime does not connect to MySQL.
- Redistribution currently uses a transparent feasible heuristic, not a global OR-Tools optimization.
- Discount response scenarios use a configurable scenario curve, not a trained price-response model.
- Anomaly alerts and some scenario/outcome collections remain in-process starter logic and are not all persistent.
- The CSV inventory endpoint validates the input file; it is not yet a complete transactional bulk-import workflow.
- The seeded dataset is fictional. Forecast validity depends on the quality, volume and representativeness of saved historical sales.
- This release has not been independently security-audited or verified under a production deployment workload. Configure secrets, backups, access policy, monitoring and deployment hardening before production use.

See `docs/API.md` for API details.
