#!/usr/bin/env bash
set -euo pipefail

APP_DIR="${APP_DIR:-/home/ubuntu/app}"
BRANCH="${BRANCH:-main}"

cd "${APP_DIR}"

echo "[update] fetching origin/${BRANCH}"
git fetch origin "${BRANCH}"

echo "[update] applying fast-forward only"
git pull --ff-only origin "${BRANCH}"

echo "[update] installing python dependencies"
source venv/bin/activate
pip install -r requirements.txt

echo "[update] installing systemd units"
sudo cp deploy/oracle/sales-intelligence.service /etc/systemd/system/sales-intelligence.service
sudo cp deploy/oracle/sales-mobile.service /etc/systemd/system/sales-mobile.service
sudo cp deploy/oracle/sales-reminder.service /etc/systemd/system/sales-reminder.service
sudo cp deploy/oracle/sales-reminder.timer /etc/systemd/system/sales-reminder.timer
sudo systemctl daemon-reload
sudo systemctl enable sales-intelligence sales-mobile sales-reminder.timer

echo "[update] restarting services"
sudo systemctl restart sales-intelligence
sudo systemctl restart sales-mobile
sudo systemctl restart sales-reminder.timer

echo "[update] running healthcheck"
"${APP_DIR}/deploy/oracle/healthcheck.sh"

echo "[update] complete"
