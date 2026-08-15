#!/usr/bin/env bash
set -euo pipefail

# Verify a newly provisioned Railway deployment from the host/CI side.
# No deployment-specific hostname or proxy port is hard-coded here.

PUBLIC_DOMAIN="${RAILWAY_PUBLIC_DOMAIN:-}"
TCP_DOMAIN="${RAILWAY_TCP_PROXY_DOMAIN:-}"
TCP_PORT="${RAILWAY_TCP_PROXY_PORT:-}"
TCP_APP_PORT="${RAILWAY_TCP_APPLICATION_PORT:-8080}"

[[ -n "$PUBLIC_DOMAIN" ]] || { echo "[verify] ERROR: RAILWAY_PUBLIC_DOMAIN is not set" >&2; exit 1; }
[[ -n "$TCP_DOMAIN" ]] || { echo "[verify] ERROR: RAILWAY_TCP_PROXY_DOMAIN is not set" >&2; exit 1; }
[[ "$TCP_PORT" =~ ^[0-9]+$ ]] || { echo "[verify] ERROR: RAILWAY_TCP_PROXY_PORT is not numeric" >&2; exit 1; }
[[ "$TCP_APP_PORT" == "8080" ]] || { echo "[verify] ERROR: RAILWAY_TCP_APPLICATION_PORT must be 8080" >&2; exit 1; }

BASE="https://${PUBLIC_DOMAIN}"
echo "[verify] Public domain: $PUBLIC_DOMAIN"
echo "[verify] TCP proxy: ${TCP_DOMAIN}:${TCP_PORT}"
echo "[verify] TCP application target: $TCP_APP_PORT"

curl -fsS --max-time 15 "${BASE}/health" >/dev/null
echo "[verify] /health: OK"

if curl -fsS --max-time 15 "${BASE}/ready" >/dev/null; then
  echo "[verify] /ready: OK"
else
  echo "[verify] /ready: not ready yet" >&2
  exit 1
fi

echo "[verify] Provisioning values are internally consistent."
