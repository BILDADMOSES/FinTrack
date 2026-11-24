# FinTrack

A portfolio and transaction tracker built for the Finnet technical assessment.

## Live demo

- [FinTrack web app](https://fintrack-6y5h.onrender.com/)
- [Swagger API documentation](https://fintrack-6y5h.onrender.com/docs)

### Portfolio holdings

![FinTrack holdings table and estimated value chart](docs/fintrack-dashboard.png)

### Transaction history

![FinTrack trade history and record-a-trade form](docs/fintrack-dashboard2.png)

## Architecture

FinTrack uses FastAPI for the REST API and serves a single-page interface built with HTML, CSS, and JavaScript. PostgreSQL on Neon stores analyst accounts, portfolios, and trades. Render runs the app as one web service.

## Run locally

1. Install Python 3.14 and `uv`.
2. Create a PostgreSQL database and run `backend/schema.sql` in it.
3. Set `DATABASE_URL` to your PostgreSQL connection URL and `FINTRACK_JWT_SECRET` to a randomly generated signing key in your terminal environment.
4. Run these commands from the repository root:

   ```bash
   uv sync --locked
   uv run --locked python -m uvicorn backend.main:app --port 8001
   ```

5. Open http://127.0.0.1:8001/. Swagger is available at `/docs`.

## Manual test

Register and sign in. Create a KES portfolio, buy 100 SCOM units at KES 20, then sell 30 at KES 22. Confirm the holdings show 70 units, KES 1,400 invested, and an estimated value of KES 1,540. Try selling 80 more units and confirm the API returns `409 Conflict`.

## Assumptions and trade-offs

Each portfolio belongs to one analyst and uses either KES or USD. Holdings use weighted-average cost. Estimated value uses the last recorded trade price. Future improvements could include automated tests and live market pricing.

## AI assistance

I used ChatGPT to help plan the app, draft code, and troubleshoot it. I implemented and tested the workflows in VS Code, Swagger, and the browser.