#!/usr/bin/env bash
set -euo pipefail

APP_URL="${APP_URL:-http://127.0.0.1:8501}"
SERVICE_NAME="${SERVICE_NAME:-sales-intelligence}"

echo "[healthcheck] service status"
systemctl is-active --quiet "${SERVICE_NAME}" && echo "active" || {
  systemctl status "${SERVICE_NAME}" --no-pager
  exit 1
}

echo "[healthcheck] http probe: ${APP_URL}"
curl --fail --silent --show-error --max-time 10 "${APP_URL}" >/dev/null

echo "[healthcheck] ok"
