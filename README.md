# Najiz Legal Agent

Full v1.0 implementation of the documented Najiz legal agent for Saudi legal claim drafting.

## Project Structure

- `backend/`: FastAPI backend, data pipeline, agent services, repositories, and tests
- `frontend/`: static RTL Arabic frontend
- `data/`: raw Najiz classification data and enrichment rules
- `legal_references/`: curated legal reference configuration
- `.docs/`: project source documentation

## Local Development

```bash
docker compose up --build
```

- Docker Compose now expects MongoDB to already be running on your machine at `localhost:27017`.
- Backend: `http://localhost:8000`
- Frontend: `http://localhost:3000`

## LLM Provider Switch

Choose the active model provider from `.env`:

```env
LLM_PROVIDER=openai
LLM_ENABLE=true
```

Supported values for `LLM_PROVIDER`:

- `openai`
- `gemini`

Then set the matching API key:

```env
OPENAI_API_KEY=...
```

or:

```env
GEMINI_API_KEY=....
```

The backend keeps the same prompts and orchestration flow, and only swaps the provider implementation underneath.

## Runtime Tuning

Temperatures are configurable from `.env` and are no longer hardcoded in the classifier and drafter flow:

```env
CLASSIFY_TEMPERATURE=0.2
INTERVIEW_TEMPERATURE=0.3
DRAFT_TEMPERATURE=0.4
REVIEW_TEMPERATURE=0.2
```

## Manual Backend Setup

```bash
cd backend
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
uvicorn main:app --reload
```

## Testing

Backend:

```bash
cd backend
pytest
```

Frontend:

```bash
cd frontend
npm install
npm run test:e2e
```

## GitHub Actions

- Every pull request to `main` runs backend `pytest` and frontend Playwright checks.
- Every push to `main` runs the same checks and then deploys the merged `main` branch to the VPS.
- The main deploy expects these repository secrets:
  - `VPS_HOST`
  - `VPS_PASSWORD`
  - `DEPLOY_ENV_FILE` or the legacy `STAGING_ENV_FILE`
 
  [![Main Deploy](https://github.com/BandAI-sa/najiz-editor/actions/workflows/main.yml/badge.svg)](https://github.com/BandAI-sa/najiz-editor/actions/workflows/main.yml)

Use [deploy/staging.env.example](deploy/staging.env.example) as the template for the deploy env file, replacing `YOUR_VPS_IP` and the encryption key with real values.

If the live app should deploy somewhere other than the current default directory on the VPS, set the repository variable `DEPLOY_APP_DIR`.
