# ChronoStock

AI-powered market intelligence that transforms stock charts into explorable narratives. Instead of showing price in isolation, ChronoStock overlays real-world news events directly onto the timeline so you can instantly see what drove every major move.

**Guests** see the live price chart and key fundamentals for any ticker. **Signed-in users** unlock AI-powered event analysis overlaid on the chart and a personal watchlist.

<!-- coverage:start -->
## Frontend Test Coverage

![Coverage](https://img.shields.io/badge/coverage-98.35%25-brightgreen)

| Metric | Coverage |
| --- | ---: |
| Lines | 98.35% |
| Statements | 98.35% |
| Branches | 84.89% |
| Functions | 92.55% |

_This section reports frontend Jest coverage and is updated automatically by GitHub Actions._
<!-- coverage:end -->

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

## Local Setup

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
2. Browse trending stocks on the home page — no account needed
3. Click any ticker to see its price chart and fundamentals
4. Click **Sign up** to create an account and unlock the watchlist

---

## Project Structure

```
ChronoStock/
├── backend/
│   ├── app/
│   │   ├── main.py        # FastAPI routes
│   │   ├── models.py      # Pydantic models
│   │   ├── stock.py       # yfinance data fetching
│   │   ├── auth.py        # JWT + bcrypt
│   │   ├── database.py    # SQLite (users, watchlist)
│   │   └── cache.py       # File-based cache (local or S3)
│   ├── cache/             # Auto-created, gitignored
│   ├── data/              # SQLite DB, auto-created, gitignored
│   ├── requirements.txt
│   └── .env.example
└── frontend/
    ├── app/               # Next.js App Router pages
    ├── components/        # Chart, EventPanel, Navbar, etc.
    ├── contexts/          # AuthContext
    ├── lib/               # API client
    ├── types/             # Shared TypeScript types
    └── data/              # Mock data (used during development)
```

---

## Notes

- **Stock data is cached on first load** — each ticker is stored as a JSON file under `backend/cache/`. Delete the file to force a fresh fetch.
- **Trending stocks are cached for 24 hours** — stored in `backend/cache/trending.json`.
- **The AI event layer is not yet connected** — the backend returns `events: []` for now. This is the next feature to build.
- **To use mock auth for local testing**, set `NEXT_PUBLIC_MOCK_AUTH=true` in the frontend environment. Leave it unset to use real backend auth.
