#!/usr/bin/env bash
set -euo pipefail

# Optional host/CI verification. No deployment-specific hostname, port or
# application-port value is hard-coded here.

PUBLIC_DOMAIN="${RAILWAY_PUBLIC_DOMAIN:-}"
TCP_DOMAIN="${RAILWAY_TCP_PROXY_DOMAIN:-}"
TCP_PORT="${RAILWAY_TCP_PROXY_PORT:-}"
TCP_APP_PORT="${RAILWAY_TCP_APPLICATION_PORT:-${PORT:-8080}}"

[[ "$TCP_APP_PORT" =~ ^[0-9]+$ ]] || { echo "[verify] ERROR: invalid TCP application port" >&2; exit 1; }

echo "[verify] TCP application target: $TCP_APP_PORT"

if [[ -n "$PUBLIC_DOMAIN" ]]; then
  BASE="https://${PUBLIC_DOMAIN}"
  echo "[verify] Public domain: $PUBLIC_DOMAIN"
  curl -fsS --max-time 15 "${BASE}/health" >/dev/null
  echo "[verify] /health: OK"
  curl -fsS --max-time 15 "${BASE}/ready" >/dev/null
  echo "[verify] /ready: OK"
else
  echo "[verify] Public domain is not currently exposed; local/runtime verification only."
fi

if [[ -n "$TCP_DOMAIN" ]]; then
  [[ "$TCP_PORT" =~ ^[0-9]+$ ]] || { echo "[verify] ERROR: TCP proxy port is not numeric" >&2; exit 1; }
  echo "[verify] TCP proxy: ${TCP_DOMAIN}:${TCP_PORT}"
else
  echo "[verify] TCP Proxy is not currently exposed."
fi

echo "[verify] Runtime values are internally consistent."
