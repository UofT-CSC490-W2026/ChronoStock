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

![Backend Coverage](https://img.shields.io/badge/backend%20coverage-98.68%25-brightgreen)

| Metric | Coverage |
| --- | ---: |
| Lines | 98.68% |
| Statements | 99.75% |
| Branches | 94.25% |
| Functions | N/A |

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

For `frontend_url`, use your expected deployed frontend origin if you already know it. If not, use a temporary placeholder and update `/home/ec2-user/backend.env` after the frontend is deployed.

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

The bootstrap process also installs `/home/ec2-user/run_full_event_pipeline.sh` for a full reproducible pipeline run. That helper script refreshes benchmark price history, runs data ingestion, runs data cleaning, and then executes the event pipeline to generate model outputs from the prepared initial data.

### 5. HTTPS setup

The instance includes a helper script at `/home/ec2-user/setup_https.sh` that installs nginx and certbot, validates nginx config, reloads nginx, and requests a certificate using `certbot_email`.

Only run this script after you have obtained a domain/subdomain for the backend and pointed its DNS record to the EC2 public IP.

Before running the script:

- Verify the domain configured in the script matches your deployment domain
- Wait for DNS propagation to complete
- Ensure the instance is reachable

### 6. Frontend deployment

The frontend is deployed separately on Vercel.

Required Vercel environment variables:

```env
NEXT_PUBLIC_MOCK_AUTH=false
# Set this after your backend HTTPS domain is ready.
NEXT_PUBLIC_API_URL=
```

Recommended Vercel project settings:

- Root directory: `frontend`
- Install command: `npm install`
- Build command: `npm run build`
- Framework preset: Next.js

Deployment flow:

1. Import the repository into Vercel
2. Set the root directory to `frontend`
3. Add the environment variables above; you can leave `NEXT_PUBLIC_API_URL` empty until your backend HTTPS domain is ready
4. Deploy the project
5. After the frontend is deployed, update `/home/ec2-user/backend.env` on the EC2 instance so `FRONTEND_URL` matches the deployed frontend URL
6. Rerun `/home/ec2-user/run_backend.sh` so the backend picks up the new CORS origin
7. Once your backend domain is available, set `NEXT_PUBLIC_API_URL` in Vercel to that backend HTTPS URL and redeploy the frontend

- Frontend app: https://chrono-stock2.vercel.app/

Point `frontend_url` in Terraform at the frontend origin that should be allowed by backend CORS.

### 7. Backend domain and frontend connectivity

The backend is deployed on AWS EC2 and exposed through a custom HTTPS domain:

- Backend API: `https://api.chronostock.shop`

The custom domain is required for the hosted frontend:

- The frontend is served over HTTPS on Vercel
- Browsers block mixed-content requests from an HTTPS frontend to an HTTP backend
- Backend CORS depends on the deployed frontend origin configured in `frontend_url`

If you deploy your own backend, you must first obtain a domain name or subdomain for it.

To connect a deployed frontend to your own backend:

1. Obtain a domain/subdomain for your backend
2. Point your backend domain DNS record at the EC2 public IP
3. Wait for that DNS record to propagate to the EC2 public IP
4. Ensure the nginx/certbot helper script is configured for that domain
5. Run `/home/ec2-user/setup_https.sh` only after DNS propagation is complete
6. Set `NEXT_PUBLIC_API_URL` in Vercel to that backend HTTPS domain
7. If `/home/ec2-user/backend.env` still has a placeholder `FRONTEND_URL`, update it to the deployed frontend URL and rerun `/home/ec2-user/run_backend.sh`

For local development, the frontend can call `http://localhost:8000` instead of the deployed API.

---

## Project Structure

```text
ChronoStock/
|- backend/                  FastAPI backend, data pipeline jobs, tests, and container setup.
|  |- app/                   Main backend package.
|  |  |- main.py             API entrypoint with routes, CORS, auth flows, and startup logic.
|  |  |- models.py           Shared request/response schemas.
|  |  |- stock.py            Stock price, company metadata, news, and earnings helpers.
|  |  |- auth.py             Password hashing and JWT utilities.
|  |  |- database.py         Database connection and initialization helpers.
|  |  |- edgar.py            SEC filing retrieval logic.
|  |  |- macro.py            Macro indicator collection and formatting.
|  |  \- pipelines/          Batch jobs for ingestion, cleaning, and event generation.
|  |     |- data_ingestion.py             Pulls raw market and news data.
|  |     |- data_cleaning.py              Cleans/filter news before modeling.
|  |     |- run_daily_update.py           Daily refresh for cached stock data.
|  |     |- run_hourly_update.py          Hourly price refresh job.
|  |     |- run_monthly_event_pipeline.py Monthly S3-backed incremental pipeline.
|  |     |- run_s3_event_pipeline.py      Per-ticker event generation from prepared data.
|  |     \- core/                         Core CAR, event detection, and LLM logic.
|  |- demodata/              Sample data for demos and tests.
|  |- depth_test/            Experimental event-detection tests.
|  |- scripts/               Backend helper scripts.
|  |- tests/                 Backend pytest suite.
|  |- Dockerfile             Backend image definition.
|  \- requirements.txt       Python dependency list.
|- frontend/                 Next.js frontend deployed on Vercel.
|  |- app/                   App Router pages.
|  |  |- page.tsx            Landing page with search and trending tickers.
|  |  |- stock/              Stock details and stock news pages.
|  |  |- market/             Market overview page.
|  |  |- compare/            Multi-stock comparison page.
|  |  |- watchlist/          User watchlist page.
|  |  |- login/ signup/ forgot-password/ reset-password/  Auth-related routes.
|  |  \- layout.tsx          Shared frontend layout.
|  |- components/            Reusable charts and UI components.
|  |- contexts/              React auth context.
|  |- lib/                   API client and frontend integration helpers.
|  |- data/                  Mock/frontend seed data.
|  |- __tests__/             Frontend Jest tests.
|  |- package.json           Frontend scripts and dependencies.
|  \- next.config.ts         Next.js configuration.
|- Terraform/                AWS infrastructure for EC2, RDS, S3, secrets, and schedulers.
|  |- main.tf                Top-level infrastructure composition.
|  |- variables.tf           Deployment inputs such as URLs, secrets, and ticker lists.
|  |- outputs.tf             Exported deployment values.
|  |- modules/               Reusable Terraform modules.
|  \- bootstrap/             Backend resources for Terraform state bootstrap.
|- scripts/                  Repository-level helper scripts.
|- assignments/              Course assignment snapshots kept in the repo.
|- tests/                    Additional top-level tests.
\- README.md                 Project setup, deployment, and usage guide.
```

---

## Notes

- **Stock data is cached on first load** - each ticker is stored as a JSON file under `backend/cache/`. Delete the file to force a fresh fetch.
- **Trending stocks are cached for 24 hours** - stored in `backend/cache/trending.json`.
- **The AI event layer is not yet connected** - the backend returns `events: []` for now. This is the next feature to build.
- **To use mock auth for local testing**, set `NEXT_PUBLIC_MOCK_AUTH=true` in the frontend environment. Leave it unset to use real backend auth.
