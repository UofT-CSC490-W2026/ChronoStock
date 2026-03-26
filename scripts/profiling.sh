#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"

set -a
source "${ROOT}/backend/.env"
set +a

conda_base="$(conda info --base)"
# shellcheck disable=SC1091
source "${conda_base}/etc/profile.d/conda.sh"
conda activate chronostock

cd "${ROOT}/backend"
python -m app.profiling "$@"

