#!/usr/bin/env bash
set -euo pipefail

APP_DIR="${APP_DIR:-/home/ubuntu/app}"
SERVICE_NAME="${SERVICE_NAME:-sales-intelligence}"
BRANCH="${BRANCH:-main}"

cd "${APP_DIR}"

echo "[update] fetching origin/${BRANCH}"
git fetch origin "${BRANCH}"

echo "[update] applying fast-forward only"
git pull --ff-only origin "${BRANCH}"

echo "[update] installing python dependencies"
source venv/bin/activate
pip install -r requirements.txt

echo "[update] restarting ${SERVICE_NAME}"
sudo systemctl restart "${SERVICE_NAME}"

echo "[update] running healthcheck"
"${APP_DIR}/deploy/oracle/healthcheck.sh"

echo "[update] complete"
