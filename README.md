# ChronoStock

AI-powered market intelligence that transforms stock charts into explorable narratives. Instead of showing price in isolation, ChronoStock overlays real-world news events directly onto the timeline so you can instantly see what drove every major move.

**Guests** see the live price chart and key fundamentals for any ticker. **Signed-in users** unlock AI-powered event analysis overlaid on the chart and a personal watchlist.

<!-- coverage:start -->
## Frontend Test Coverage

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
## Backend Test Coverage

![Backend Coverage](https://img.shields.io/badge/backend%20coverage-98.86%25-brightgreen)

| Metric | Coverage |
| --- | ---: |
| Lines | 98.86% |
| Statements | 100.00% |
| Branches | 94.35% |

_This section reports backend pytest-cov coverage and is updated automatically by GitHub Actions._
<!-- backend-coverage:end -->

---

## Tech Stack

| Layer | Technology |
|---|---|
| Frontend | Next.js 15, Tailwind CSS, Lightweight Charts (TradingView) |
| Backend | FastAPI, Python 3.10+ |
| Market data | yfinance, yahooquery |
| Auth | JWT (python-jose) + bcrypt |
| Cache | Local JSON files (swappable to AWS S3) |
| Database | SQLite (users & watchlists) |

---

## Local Run

### Prerequisites

- Node.js 18+
- Python 3.10+ (conda or venv)
- Git

---

### 1. Clone the repo

```bash
git clone https://github.com/QixiangFan/ChronoStock.git
cd ChronoStock
```

---

### 2. Backend

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

Open `.env` and set a secret key for JWT:

```env
JWT_SECRET_KEY=any-long-random-string-you-choose
```

Optional backend variables for local development:

```env
FRONTEND_URL=http://localhost:3000
DB_BACKEND=sqlite
```

Start the API server:

```bash
uvicorn app.main:app --reload --port 8000
```

The API is now running at `http://localhost:8000`.
Interactive API docs available at `http://localhost:8000/docs`.

---

### 3. Frontend

Open a new terminal:

```bash
cd frontend

# Install dependencies
npm install

# Start the dev server
npm run dev
```

The app is now running at `http://localhost:3000`.

---

### 4. Try it out

1. Open `http://localhost:3000`
2. Browse trending stocks on the home page - no account needed
3. Click any ticker to see its price chart and fundamentals
4. Click **Sign up** to create an account and unlock the watchlist

---

## Terraform Deployment

This repository also includes AWS infrastructure under `Terraform/` for an EC2 + RDS + S3 deployment.

### Prerequisites

- Terraform 1.5+
- AWS credentials configured locally
- An existing AWS EC2 key pair in the target region
- A domain name if you want to enable HTTPS with Certbot

### 1. Prepare a tfvars file

```bash
cd Terraform
cp dev.tfvars.example dev.tfvars
```

For a production deployment, copy `prod.tfvars.example` to `prod.tfvars` instead.

Fill in the placeholder values before running Terraform:

- `key_name`
- `db_password`
- `bucket_name`
- `pipeline_source_bucket_name`
- `polygon_api_key`
- `llm_api_key`
- `jwt_secret_key`
- `secret_name`
- `frontend_url`
- `certbot_email`
- `monthly_event_tickers`

Do not commit populated `dev.tfvars` or `prod.tfvars` files.

### 2. Apply the infrastructure

```bash
terraform init
terraform plan -var-file="dev.tfvars"
terraform apply -var-file="dev.tfvars"
```

Useful outputs:

```bash
terraform output ec2_public_ip
terraform output rds_host
terraform output rds_port
```

### 3. What Terraform configures

- An EC2 instance that pulls and runs the backend Docker image
- An RDS PostgreSQL database
- S3 buckets for application and pipeline data
- AWS Secrets Manager values consumed by the EC2 bootstrap script
- CloudWatch logging plus EventBridge Scheduler jobs for daily, hourly, and monthly pipelines

### 4. EC2 bootstrap behavior

During instance startup, the EC2 `user_data` script:

- Fetches database and API secrets from AWS Secrets Manager
- Writes `/home/ec2-user/backend.env`
- Starts the backend container on port `8000`
- Installs helper scripts for daily, hourly, and monthly pipeline runs

The monthly event pipeline reads the ticker list from `monthly_event_tickers` in your tfvars file.

### 5. HTTPS setup

The instance includes a helper script at `/home/ec2-user/setup_https.sh` that installs nginx and certbot, validates nginx config, reloads nginx, and requests a certificate using `certbot_email`.

If you use this script:

- Point your domain DNS to the EC2 public IP first
- Verify the domain configured in the script matches your deployment domain
- Run the script manually after the instance is reachable

### 6. Frontend deployment

The frontend is currently deployed separately:

- Frontend app: https://chrono-stock2.vercel.app/

Point `frontend_url` in Terraform at the frontend origin that should be allowed by backend CORS.

---

## Project Structure

```text
ChronoStock/
|- .github/
|  \- workflows/
|- backend/
|  |- app/
|  |  |- analysis.py
|  |  |- auth.py
|  |  |- benchmark.py
|  |  |- cache.py
|  |  |- database.py
|  |  |- demo_events.py
|  |  |- edgar.py
|  |  |- macro.py
|  |  |- main.py
|  |  |- models.py
|  |  |- profiling.py
|  |  |- stock.py
|  |  \- pipelines/
|  |     |- core/
|  |     |  |- car.py
|  |     |  |- event_detection.py
|  |     |  \- llm.py
|  |     |- data_cleaning.py
|  |     |- data_ingestion.py
|  |     |- run_daily_update.py
|  |     |- run_event_pipeline.py
|  |     |- run_hourly_update.py
|  |     |- run_monthly_event_pipeline.py
|  |     \- run_s3_event_pipeline.py
|  |- cache/
|  |- data/
|  |- demodata/
|  |- tests/
|  |- Dockerfile
|  |- pytest.ini
|  \- requirements.txt
|- frontend/
|  |- __mocks__/
|  |- __tests__/
|  |- app/
|  |- components/
|  |- contexts/
|  |- lib/
|  |- public/
|  |- types/
|  |- jest.config.ts
|  \- package.json
|- scripts/
|- Terraform/
\- README.md
```

---

## Notes

- **Stock data is cached on first load** - each ticker is stored as a JSON file under `backend/cache/`. Delete the file to force a fresh fetch.
- **Trending stocks are cached for 24 hours** - stored in `backend/cache/trending.json`.
- **The AI event layer is not yet connected** - the backend returns `events: []` for now. This is the next feature to build.
- **To use mock auth for local testing**, set `NEXT_PUBLIC_MOCK_AUTH=true` in the frontend environment. Leave it unset to use real backend auth.
