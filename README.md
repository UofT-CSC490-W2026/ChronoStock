# ChronoStock

AI-powered market intelligence that transforms stock charts into explorable narratives. Instead of showing price in isolation, ChronoStock overlays real-world news events directly onto the timeline so you can instantly see what drove every major move.

**Guests** see the live price chart and key fundamentals for any ticker. **Signed-in users** unlock AI-powered event analysis overlaid on the chart, market overview with AI narrative, and a personal watchlist.

- **Live app:** https://chrono-stock2.vercel.app/
- **Backend API:** https://api.chronostock.shop
- **API docs:** https://api.chronostock.shop/docs

---

## Table of Contents

- [Tech Stack](#tech-stack)
- [Architecture Overview](#architecture-overview)
- [How to Run Locally](#how-to-run-locally)
- [Testing](#testing)
- [Benchmarking](#benchmarking)
- [CI/CD](#cicd)
- [Infrastructure as Code (Terraform)](#infrastructure-as-code-terraform)
- [Frontend Deployment (Vercel)](#frontend-deployment-vercel)
- [Project Structure](#project-structure)
- [Test Coverage](#test-coverage)

---

## Tech Stack

| Layer | Technology |
|---|---|
| Frontend | Next.js 15, React 19, Tailwind CSS, Lightweight Charts (TradingView) |
| Backend | FastAPI, Python 3.12, Uvicorn |
| Market Data | yfinance, yahooquery |
| AI / LLM | AWS Bedrock (Claude), DeepSeek API |
| Event Detection | ruptures (change-point detection), scikit-learn (CAR market model) |
| Auth | JWT (python-jose) + bcrypt |
| Cache | Multi-backend: local JSON, AWS S3, or Redis (with L1 in-memory LRU) |
| Database | SQLite (local dev) / PostgreSQL via RDS (production) |
| Infrastructure | Terraform, Docker, AWS (EC2, RDS, S3, EventBridge, CloudWatch, Secrets Manager) |
| CI/CD | GitHub Actions (coverage badges, Docker image builds) |
| Testing | Jest + React Testing Library (frontend), pytest + pytest-benchmark (backend) |

---

## Architecture Overview

```
                           +------------------+
                           |   Vercel (HTTPS) |
                           |   Next.js 15     |
                           +--------+---------+
                                    |
                               REST API
                                    |
                   +----------------v-----------------+
                   |       AWS EC2 (Docker)           |
                   |       FastAPI Backend             |
                   |  +-----------+-----------+       |
                   |  | REST API  | Pipelines |       |
                   |  +-----------+-----------+       |
                   +---+-------+-------+------+-------+
                       |       |       |      |
              +--------+  +----+  +----+  +---+--------+
              |           |       |       |            |
         RDS Postgres   S3    yfinance  FRED API   AWS Bedrock
         (users,       (cache, (market  (macro      (AI narrative,
          watchlists,   pipeline data)  indicators)  event analysis)
          events)       data)
```

**Event Detection Pipeline:** The core intelligence layer detects significant stock price movements using change-point detection (ruptures), computes Cumulative Abnormal Returns (CAR) via a market model regression, and uses LLM-based news filtering to match events to their real-world causes. Pipelines run on automated schedules via AWS EventBridge (daily, hourly, monthly).

---

## How to Run Locally

### Prerequisites

- Node.js 18+
- Python 3.10+ (conda or venv)
- Git

### Quick Start (all-in-one)

```bash
git clone https://github.com/UofT-CSC490-W2026/ChronoStock.git
cd ChronoStock

# Set up backend environment
cd backend
conda create -n chronostock python=3.12   # or: python -m venv .venv && source .venv/bin/activate
conda activate chronostock
pip install -r requirements.txt
cp .env.example .env
# Edit .env and set JWT_SECRET_KEY to any long random string
cd ..

# Set up frontend
cd frontend
npm install
cd ..

# Start everything (backend on :8000, frontend on :3000)
./scripts/start.sh
```

Open http://localhost:3000 to use the app.

### Step-by-Step Setup

#### 1. Clone the repo

```bash
git clone https://github.com/UofT-CSC490-W2026/ChronoStock.git
cd ChronoStock
```

#### 2. Backend

```bash
cd backend

# Create and activate a Python environment
conda create -n chronostock python=3.12   # or use venv
conda activate chronostock

# Install dependencies
pip install -r requirements.txt

# Create your .env file
cp .env.example .env
```

Open `.env` and set the required variable:

```env
JWT_SECRET_KEY=any-long-random-string-you-choose
```

Optional variables for local development (defaults are fine for most use cases):

```env
FRONTEND_URL=http://localhost:3000   # CORS origin
DB_BACKEND=sqlite                    # sqlite (default) or postgres
CACHE_BACKEND=local                  # local (default), s3, or redis
```

For full feature support, you can also set:

```env
FRED_API_KEY=your-key                # Macroeconomic data on /api/market-summary
SEC_USER_AGENT_EMAIL=your@email.com  # SEC EDGAR filing access
AWS_BEARER_TOKEN_BEDROCK=your-key    # AI market analysis (auth-protected)
BEDROCK_MODEL_ID=us.anthropic.claude-haiku-4-5-20251001-v1:0
```

See `backend/.env.example` for the full list of configuration options.

Start the API server:

```bash
uvicorn app.main:app --reload --port 8000
```

The API is now running at http://localhost:8000. Interactive API docs at http://localhost:8000/docs.

#### 3. Frontend

Open a new terminal:

```bash
cd frontend
npm install
npm run dev
```

The app is now running at http://localhost:3000.

#### 4. Try it out

1. Open http://localhost:3000
2. Browse trending stocks on the home page (no account needed)
3. Click any ticker to see its price chart, fundamentals, news, earnings, and SEC filings
4. Click **Sign up** to create an account and unlock the watchlist and AI event analysis
5. Visit the **Market** page for macroeconomic overview with AI narrative (requires FRED/Bedrock keys)
6. Use the **Compare** page to view multiple stocks side by side

---

## Testing

### Frontend Tests

```bash
cd frontend
npm test                  # Run all Jest tests
npm run test:watch        # Watch mode
npm run test:coverage     # Generate coverage report
```

- **Framework:** Jest 30 + React Testing Library
- **Environment:** jsdom
- **Test directory:** `frontend/__tests__/`
- **Current coverage:** 99.08% lines, 85.55% branches, 91.33% functions

### Backend Tests

```bash
cd backend
pytest                                          # Run all tests
pytest -v                                       # Verbose output
pytest --cov=app --cov-report=html              # With HTML coverage report
pytest --cov=app --cov-report=term-missing      # Coverage with line details
```

- **Framework:** pytest + pytest-cov
- **Test directory:** `backend/tests/`
- **Config:** `backend/pytest.ini`
- **Current coverage:** 99.17% lines, 100% statements, 95.79% branches

Test modules cover: authentication, database operations, data cleaning, event detection (CAR + change-point), LLM integration, daily update pipeline, S3 event pipeline, profiling, and analysis.

---

## Benchmarking

API endpoint performance is measured using `pytest-benchmark`. The benchmark suite warms up the cache before measurement to isolate endpoint latency from external API calls.

### Run benchmarks

```bash
# Using the helper script (activates conda env automatically)
./scripts/benchmark.sh

# Or manually
cd backend
pytest app/benchmark.py -v
pytest app/benchmark.py -v --benchmark-sort=mean       # Sort by mean time
pytest app/benchmark.py -v --benchmark-compare          # Compare against saved runs
```

The benchmark requires `AUTH_EMAIL` and `AUTH_PASSWORD` set in `backend/.env` for auth-protected endpoints.

### Benchmarked endpoints

| Endpoint | Description |
|---|---|
| `GET /health` | Health check |
| `GET /api/trending` | Trending stock tickers |
| `GET /api/prices?tickers=AAPL` | OHLC price data |
| `GET /api/stock/AAPL` | Company metadata and fundamentals |
| `GET /api/news/AAPL` | Company news feed |
| `GET /api/earnings/AAPL` | Earnings history |
| `GET /api/sec/AAPL` | SEC filing links |
| `GET /api/search?q=AAPL` | Ticker search |
| `GET /api/market-summary` | Macroeconomic indicators |
| `GET /api/indicator/VIX` | Individual indicator data |
| `GET /api/market-analysis` | AI-generated market narrative (auth) |
| `GET /auth/me` | Current user info (auth) |
| `GET /api/watchlist` | User watchlist (auth) |
| `POST /api/watchlist/AAPL` | Add to watchlist (auth) |
| `DELETE /api/watchlist/AAPL` | Remove from watchlist (auth) |

You can override the default ticker and indicator:

```bash
TICKER=MSFT INDICATOR=DGS10 pytest app/benchmark.py -v
```

### Profiling

```bash
# Using the helper script
./scripts/profiling.sh

# Or manually
cd backend
python -m app.profiling
```

---

## CI/CD

Three GitHub Actions workflows automate quality checks and deployment:

| Workflow | Trigger | What it does |
|---|---|---|
| `frontend-coverage.yml` | Push to main, PRs | Runs Jest coverage, auto-updates README badge |
| `backend-coverage.yml` | Push to main, PRs | Runs pytest-cov, auto-updates README badge |
| `chronostock-backend-docker.yml` | Push to main, manual dispatch | Builds and pushes Docker image to Docker Hub |

Coverage badges in this README are updated automatically on every push to `main`.

---

## Infrastructure as Code (Terraform)

The `Terraform/` directory contains a complete AWS deployment using modular Terraform:

```
Terraform/
|- main.tf              Top-level infrastructure composition
|- variables.tf         Deployment inputs (URLs, secrets, ticker lists)
|- outputs.tf           Exported values (EC2 IP, RDS host/port)
|- modules/
|  |- ec2/              EC2 instance for backend container
|  |- rds/              PostgreSQL database
|  |- s3/               S3 buckets for cache and pipeline data
|  |- vpc/              VPC and networking
|  |- security_group/   Security group rules
|  \- secrets/          AWS Secrets Manager integration
\- bootstrap/           Resources for Terraform state backend
```

### Prerequisites

- Terraform 1.5+
- AWS credentials configured locally
- An existing AWS EC2 key pair in the target region

### Deploy

```bash
cd Terraform
cp dev.tfvars.example dev.tfvars
# Edit dev.tfvars with your values (see variables.tf for full list)

terraform init
terraform plan -var-file="dev.tfvars"
terraform apply -var-file="dev.tfvars"
```

Key outputs:

```bash
terraform output ec2_public_ip
terraform output rds_host
terraform output rds_port
```

### What Terraform provisions

- **EC2 instance** running the backend Docker container on port 8000
- **RDS PostgreSQL** database for users, watchlists, and event data
- **S3 buckets** for application cache and pipeline input/output data
- **AWS Secrets Manager** for database credentials and API keys
- **CloudWatch** logging and monitoring
- **EventBridge Scheduler** jobs for daily, hourly, and monthly pipelines

### EC2 bootstrap behavior

The EC2 `user_data` script automatically:

1. Fetches secrets from AWS Secrets Manager
2. Writes `/home/ec2-user/backend.env` with all runtime configuration
3. Pulls and starts the backend Docker container
4. Installs helper scripts for pipeline execution

The bootstrap also installs `/home/ec2-user/run_full_event_pipeline.sh` for a **full reproducible pipeline run**. This script refreshes benchmark price history, runs data ingestion, runs data cleaning, and executes the event pipeline to generate model outputs from prepared data.

### HTTPS setup

After pointing a domain's DNS to the EC2 public IP:

```bash
# On the EC2 instance, after DNS propagation
/home/ec2-user/setup_https.sh
```

This installs nginx + certbot and provisions a TLS certificate.

### Required tfvars

See `dev.tfvars.example` for the full template. Key variables:

| Variable | Purpose |
|---|---|
| `key_name` | AWS EC2 key pair name |
| `db_password` | PostgreSQL password |
| `bucket_name` | S3 cache bucket |
| `jwt_secret_key` | Backend JWT secret |
| `frontend_url` | Deployed frontend origin (CORS) |
| `llm_api_key` | LLM API key (DeepSeek) |
| `fred_api_key` | FRED macroeconomic data |
| `aws_bearer_token_bedrock` | AWS Bedrock API key |
| `monthly_event_tickers` | Tickers for monthly event pipeline |
| `certbot_email` | Email for HTTPS certificate |

Do not commit populated `dev.tfvars` or `prod.tfvars` files.

---

## Frontend Deployment (Vercel)

The frontend is deployed separately on Vercel.

### Vercel environment variables

```env
NEXT_PUBLIC_MOCK_AUTH=false
NEXT_PUBLIC_API_URL=https://your-backend-domain.com
```

### Vercel project settings

- **Root directory:** `frontend`
- **Install command:** `npm install`
- **Build command:** `npm run build`
- **Framework preset:** Next.js

### Deployment flow

1. Import the repository into Vercel and set root directory to `frontend`
2. Add environment variables (`NEXT_PUBLIC_API_URL` can be set later)
3. Deploy the project
4. Update `FRONTEND_URL` in `/home/ec2-user/backend.env` on EC2 to match the Vercel URL
5. Rerun `/home/ec2-user/run_backend.sh` so the backend picks up the new CORS origin
6. Once the backend HTTPS domain is ready, set `NEXT_PUBLIC_API_URL` in Vercel and redeploy

---

## Project Structure

```text
ChronoStock/
|- backend/                  FastAPI backend, data pipelines, tests, and Docker setup
|  |- app/                   Main backend package
|  |  |- main.py             API entrypoint with routes, CORS, auth, and startup logic
|  |  |- models.py           Pydantic request/response schemas
|  |  |- stock.py            Stock price, company metadata, news, and earnings helpers
|  |  |- auth.py             Password hashing and JWT utilities
|  |  |- database.py         Database abstraction (SQLite / PostgreSQL)
|  |  |- cache.py            Multi-backend cache (local / S3 / Redis) with L1 LRU
|  |  |- edgar.py            SEC EDGAR filing retrieval
|  |  |- macro.py            Macroeconomic indicator collection (FRED API)
|  |  |- analysis.py         Data analysis utilities
|  |  |- benchmark.py        API endpoint benchmark suite (pytest-benchmark)
|  |  |- profiling.py        Performance profiling utilities
|  |  \- pipelines/          Batch jobs for ingestion, cleaning, and event generation
|  |     |- data_ingestion.py             Pulls raw market and news data
|  |     |- data_cleaning.py              Cleans and filters news before modeling
|  |     |- run_daily_update.py           Daily refresh for cached stock data
|  |     |- run_hourly_update.py          Hourly price refresh job
|  |     |- run_monthly_event_pipeline.py Monthly S3-backed incremental pipeline
|  |     |- run_s3_event_pipeline.py      Per-ticker event generation from prepared data
|  |     \- core/                         Core ML and LLM logic
|  |        |- car.py                     Cumulative Abnormal Returns (market model)
|  |        |- event_detection.py         Change-point detection (ruptures)
|  |        \- llm.py                     LLM-based news filtering and classification
|  |- tests/                 Backend pytest suite
|  |- demodata/              Sample data for demos and tests
|  |- Dockerfile             Backend Docker image definition
|  \- requirements.txt       Python dependency list
|- frontend/                 Next.js frontend deployed on Vercel
|  |- app/                   App Router pages
|  |  |- page.tsx            Landing page with search and trending tickers
|  |  |- stock/              Stock detail and news pages
|  |  |- market/             Market overview with AI narrative
|  |  |- compare/            Multi-stock comparison page
|  |  |- watchlist/          User watchlist page (auth required)
|  |  |- login/ signup/ forgot-password/ reset-password/  Auth routes
|  |  \- layout.tsx          Shared layout
|  |- components/            Reusable charts and UI components
|  |- contexts/              React auth context
|  |- lib/                   API client and helpers
|  |- data/                  Mock/seed data
|  |- __tests__/             Frontend Jest test suite
|  \- package.json           Scripts and dependencies
|- Terraform/                AWS infrastructure (EC2, RDS, S3, secrets, schedulers)
|  |- main.tf                Top-level infrastructure composition
|  |- variables.tf           Deployment inputs
|  |- outputs.tf             Exported deployment values
|  |- modules/               Reusable Terraform modules (ec2, rds, s3, vpc, security_group, secrets)
|  \- bootstrap/             Terraform state backend resources
|- scripts/                  Repository-level helper scripts
|  |- start.sh               Start full stack (Redis optional, backend, frontend)
|  |- benchmark.sh           Run API endpoint benchmarks
|  \- profiling.sh           Run performance profiling
|- .github/workflows/        CI/CD pipelines (coverage badges, Docker builds)
\- README.md                 This file
```

---

## Test Coverage

<!-- coverage:start -->
### Frontend Test Coverage

![Coverage](https://img.shields.io/badge/coverage-99.08%25-brightgreen)

| Metric | Coverage |
| --- | ---: |
| Lines | 99.08% |
| Statements | 99.08% |
| Branches | 85.55% |
| Functions | 91.33% |

_This section reports frontend Jest coverage and is updated automatically by GitHub Actions._
<!-- coverage:end -->

<!-- backend-coverage:start -->
### Backend Test Coverage

![Backend Coverage](https://img.shields.io/badge/backend%20coverage-99.17%25-brightgreen)

| Metric | Coverage |
| --- | ---: |
| Lines | 99.17% |
| Statements | 100.00% |
| Branches | 95.79% |
| Functions | N/A |

_This section reports backend pytest-cov coverage and is updated automatically by GitHub Actions._
<!-- backend-coverage:end -->

---

## Notes

- **Stock data is cached on first load** -- each ticker is stored as a JSON file under `backend/cache/`. Delete the file to force a fresh fetch.
- **Trending stocks are cached for 24 hours** -- stored in `backend/cache/trending.json`.
- **To use mock auth for local testing**, set `NEXT_PUBLIC_MOCK_AUTH=true` in the frontend environment. Leave it unset to use real backend auth.
