#!/usr/bin/env bash
# Start ChronoStock backend + frontend in one command.
# Usage: ./start.sh

set -e
ROOT="$(cd "$(dirname "$0")" && pwd)"

# ── Colours ───────────────────────────────────────────────────────────────────
CYAN='\033[0;36m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m'

echo -e "${CYAN}"
echo "  ╔══════════════════════════════════╗"
echo "  ║     ChronoStock  Dev  Server     ║"
echo "  ╚══════════════════════════════════╝"
echo -e "${NC}"

# ── Activate conda env ────────────────────────────────────────────────────────
CONDA_BASE="$(conda info --base 2>/dev/null || true)"
if [ -z "$CONDA_BASE" ]; then
  echo -e "${RED}Error: conda not found. Make sure conda is installed and on your PATH.${NC}"
  exit 1
fi

source "$CONDA_BASE/etc/profile.d/conda.sh"

if ! conda activate chronostock 2>/dev/null; then
  echo -e "${RED}Error: conda environment 'chronostock' not found.${NC}"
  echo "Create it with:  conda create -n chronostock python=3.12"
  echo "Then install:    pip install -r backend/requirements.txt"
  exit 1
fi

echo -e "${GREEN}✓ conda env 'chronostock' activated${NC}"

# ── Check .env ────────────────────────────────────────────────────────────────
if [ ! -f "$ROOT/backend/.env" ]; then
  echo -e "${YELLOW}Warning: backend/.env not found — copying from .env.example${NC}"
  cp "$ROOT/backend/.env.example" "$ROOT/backend/.env"
  echo "  Edit backend/.env and set JWT_SECRET_KEY before using auth features."
fi

# ── Backend ───────────────────────────────────────────────────────────────────
echo -e "${GREEN}→ Starting backend  →  http://localhost:8000${NC}"
cd "$ROOT/backend"
uvicorn app.main:app --reload --port 8000 &
BACKEND_PID=$!

# Give the backend a moment to bind the port
sleep 1

# ── Frontend ──────────────────────────────────────────────────────────────────
echo -e "${GREEN}→ Starting frontend →  http://localhost:3000${NC}"
cd "$ROOT/frontend"
npm run dev &
FRONTEND_PID=$!

echo ""
echo -e "${YELLOW}Both servers running. Press Ctrl+C to stop.${NC}"
echo ""

# ── Cleanup on Ctrl+C / exit ──────────────────────────────────────────────────
cleanup() {
  echo ""
  echo "Stopping servers…"
  kill "$BACKEND_PID"  2>/dev/null || true
  kill "$FRONTEND_PID" 2>/dev/null || true
  wait "$BACKEND_PID"  2>/dev/null || true
  wait "$FRONTEND_PID" 2>/dev/null || true
  echo "Done."
}
trap cleanup INT TERM

wait
