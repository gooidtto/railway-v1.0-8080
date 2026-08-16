#!/usr/bin/env bash
set -euo pipefail

# Verify the standard portable deployment using only current Railway runtime values.
# No deployment-specific hostname or random TCP port is hard-coded here.

PUBLIC_DOMAIN="${RAILWAY_PUBLIC_DOMAIN:-}"
TCP_DOMAIN="${RAILWAY_TCP_PROXY_DOMAIN:-}"
TCP_PORT="${RAILWAY_TCP_PROXY_PORT:-}"
TCP_APP_PORT="${RAILWAY_TCP_APPLICATION_PORT:-${PORT:-8080}}"

[[ -n "$PUBLIC_DOMAIN" ]] || { echo "[verify] ERROR: Generate Domain is not configured" >&2; exit 1; }
[[ -n "$TCP_DOMAIN" ]] || { echo "[verify] ERROR: TCP Proxy is not configured" >&2; exit 1; }
[[ "$TCP_PORT" =~ ^[0-9]+$ ]] || { echo "[verify] ERROR: TCP proxy port is not numeric" >&2; exit 1; }
[[ "$TCP_APP_PORT" == "8080" ]] || { echo "[verify] ERROR: TCP Proxy target/application port must be 8080" >&2; exit 1; }

BASE="https://${PUBLIC_DOMAIN}"
echo "[verify] Public domain: $PUBLIC_DOMAIN"
echo "[verify] TCP proxy: ${TCP_DOMAIN}:${TCP_PORT}"
echo "[verify] TCP application target: $TCP_APP_PORT"

curl -fsS --max-time 15 "${BASE}/health" >/dev/null
echo "[verify] /health: OK"
curl -fsS --max-time 15 "${BASE}/ready" >/dev/null
echo "[verify] /ready: OK"

TOKEN_FILE="/data/subscription_token.txt"
SUB_FILE="/data/subscription.txt"
if [[ -f "$TOKEN_FILE" && -f "$SUB_FILE" ]]; then
  TOKEN="$(cat "$TOKEN_FILE")"
  SUB_URL="${BASE}/sub/${TOKEN}"
  SUB_B64="$(curl -fsS --max-time 15 "$SUB_URL")"
  python3 - "$SUB_B64" <<'PY'
import base64
import sys

raw = base64.b64decode(sys.argv[1]).decode()
nodes = [line for line in raw.splitlines() if line.startswith('vless://')]
if len(nodes) != 4:
    raise SystemExit('[verify] ERROR: expected exactly 4 VLESS nodes, got %d' % len(nodes))
for needle in ('type=xhttp', 'type=raw', 'type=grpc'):
    if needle not in raw:
        raise SystemExit('[verify] ERROR: missing subscription transport: %s' % needle)
print('[verify] subscription nodes: 4')
print('[verify] transports: XHTTP/TLS + XHTTP/REALITY + RAW/Vision/REALITY + gRPC/REALITY')
PY
else
  echo "[verify] WARNING: /data subscription files are unavailable on this host; endpoint checks passed."
fi

echo "[verify] Standard Railway networking and runtime discovery: OK"
