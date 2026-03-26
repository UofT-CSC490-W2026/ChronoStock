#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"

set -a
source "${ROOT}/backend/.env"
set +a

REDIS_PID=""
BACKEND_PID=""
FRONTEND_PID=""

cleanup() {
  set +e
  [[ -n "${FRONTEND_PID}" ]] && kill "${FRONTEND_PID}" 2>/dev/null
  [[ -n "${BACKEND_PID}" ]] && kill "${BACKEND_PID}" 2>/dev/null
  [[ -n "${REDIS_PID}" ]] && kill "${REDIS_PID}" 2>/dev/null
  wait 2>/dev/null
}
trap cleanup INT TERM EXIT

if [[ "${CACHE_BACKEND:-local}" == "redis" ]]; then
  redis-server "${ROOT}/backend/redis.conf" &
  REDIS_PID="$!"
fi

conda_base="$(conda info --base)"
source "${conda_base}/etc/profile.d/conda.sh"
conda activate chronostock

cd "${ROOT}/backend"
uvicorn app.main:app --reload --port 8000 >/dev/null 2>&1 &
BACKEND_PID="$!"

cd "${ROOT}/frontend"
npm run dev >/dev/null 2>&1 &
FRONTEND_PID="$!"

echo "ChronoStock running:"
echo "- Backend:  http://localhost:8000"
echo "- Frontend: http://localhost:3000"

wait

