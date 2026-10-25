# Savora API

Business API endpoints require `Authorization: Bearer <token>`. Obtain a token with `POST /api/auth/login`; `GET /api/meta` and authentication endpoints are public. A 401 response means the session is missing or invalid.

# Savora API reference

Base URL: `http://127.0.0.1:5000/api`

All JSON request bodies are validated. Errors are returned as `{ "error": "message" }`. Starter records is synthetic and mutable state is in process memory.

| Method | Path | Notes |
|---|---|---|
| GET | `/meta` | Storage mode and synthetic-data disclosure |
| GET | `/dashboard/summary` | KPIs and category breakdown |
| GET | `/dashboard/trends` | Monthly sales/forecast series |
| GET | `/dashboard/risk-distribution` | Surplus risk counts |
| GET, POST | `/products` | List/search or create a product |
| GET, PUT | `/products/{id}` | Read/update product |
| GET | `/inventory` | Inventory rows; optional `q`, `location_id` |
| GET | `/inventory/{id}` | Inventory detail |
| GET | `/batches` | Batch records |
| GET | `/locations` | Distribution locations |
| GET | `/partners` | Recovery partners |
| GET | `/sales` | Synthetic historical sales sample |
| POST | `/forecasts/generate` | `{product_id?, location_id?, horizon_days: 7|14|30}` |
| GET | `/forecasts` | Baseline forecast with query options |
| GET | `/models/performance` | Chronological holdout metrics |
| POST | `/models/retrain` | Re-evaluate candidates; does not persist model |
| GET | `/surplus?horizon=14` | Projected surplus; optional `risk`, `category`, `location_id` |
| POST | `/surplus/recalculate` | `{horizon, demand_multiplier}` |
| GET | `/anomalies` | seeded statistical alerts |
| PATCH | `/anomalies/{id}/status` | `{status: Open|Investigating|Resolved|Dismissed}` |
| POST | `/redistribution/optimize` | `{horizon, capacity, cost_per_unit}` |
| GET | `/redistribution/plans` | Generated starter plans |
| GET | `/redistribution/plans/{id}` | Plan detail |
| POST | `/redistribution/plans/{id}/approve` | Proposed → Approved |
| POST | `/redistribution/items/{id}/dispatch` | Record dispatch state |
| POST | `/redistribution/items/{id}/complete` | Record completed state |
| POST | `/discounts/optimize` | `{product_id, horizon}` |
| POST | `/recovery/allocate` | `{horizon, partner_capacity?}` |
| GET | `/recovery/plans` | Recovery plans |
| GET | `/recovery/plans/{id}` | Recovery plan detail |
| POST | `/recovery/plans/{id}/approve` | Proposed → Approved |
| POST | `/simulations/run` | Validated what-if inputs; does not mutate inventory |
| GET, POST | `/simulations` | List or save `{name, scenario}` |
| GET, DELETE | `/simulations/{id}` | Read/delete saved scenario |
| GET, POST | `/outcomes` | Read or record `{confirmed_units, outcome_type?}` |
| POST | `/inventory/import` | Multipart CSV validation only; no persistence |
