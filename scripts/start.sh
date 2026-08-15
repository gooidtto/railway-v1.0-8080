#!/bin/sh
set -eu

DATA_DIR="${RAILWAY_VOLUME_MOUNT_PATH:-${DATA_DIR:-/data}}"
GATEWAY_PORT="${GATEWAY_PORT:-${PORT:-8080}}"
PORT="$GATEWAY_PORT" XRAY_PORT="${XRAY_PORT:-10087}" XRAY_HTTP_PORT="${XRAY_HTTP_PORT:-10086}" XRAY_LISTEN="${XRAY_LISTEN:-127.0.0.1}"
CONFIG="${XRAY_CONFIG:-/etc/xray/config.json}"
REALITY_TARGET="${REALITY_TARGET:-www.cloudflare.com:443}" REALITY_SNI="${REALITY_SNI:-${REALITY_TARGET%%:*}}" REALITY_FINGERPRINT="${REALITY_FINGERPRINT:-chrome}" XHTTP_PATH="${XHTTP_PATH:-/xhttp}" XHTTP_MODE="${XHTTP_MODE:-auto}" SHORT_ID="${SHORT_ID:-50175c035ee132}"
REALITY_SNI_LIMIT="${REALITY_SNI_LIMIT:-7}"

# Railway-provided values are authoritative. Public domain and TCP proxy
# external port are deployment-specific and must never be hard-coded.
PUBLIC_DOMAIN="${RAILWAY_PUBLIC_DOMAIN:-${PUBLIC_DOMAIN:-}}"
SERVER_HOST="${RAILWAY_TCP_PROXY_DOMAIN:-${SERVER_HOST:-${XRAY_TCP_PROXY_HOST:-}}}"
SERVER_PORT="${RAILWAY_TCP_PROXY_PORT:-${SERVER_PORT:-${XRAY_TCP_PROXY_PORT:-}}}"
TCP_APPLICATION_PORT="${RAILWAY_TCP_APPLICATION_PORT:-${TCP_APPLICATION_PORT:-8080}}"

READY_FILE="$DATA_DIR/.xray-ready"
BOOTSTRAP_FILE="$DATA_DIR/bootstrap-networking-required.txt"
TOKEN_FILE="$DATA_DIR/subscription_token.txt"
UUID_FILE="$DATA_DIR/uuid.txt"
PRIV_FILE="$DATA_DIR/reality_private_key.txt"
PUB_FILE="$DATA_DIR/reality_public_key.txt"
DEC_FILE="$DATA_DIR/vless_decryption.txt"
ENC_FILE="$DATA_DIR/vless_encryption.txt"
URL_FILE="$DATA_DIR/subscription_url.txt"

mkdir -p "$DATA_DIR" "$(dirname "$CONFIG")"
chmod 0700 "$DATA_DIR"
rm -f "$READY_FILE"

# IMPORTANT: a fresh Railway GitHub deployment does not necessarily have
# Public Domain / TCP Proxy resources yet. Do not crash-loop the container.
# Keep the HTTP gateway alive so Railway can mark the service reachable and
# the operator can create the two networking resources in Settings.
NETWORK_BOOTSTRAP_REQUIRED=0
if [ -z "$PUBLIC_DOMAIN" ]; then
  NETWORK_BOOTSTRAP_REQUIRED=1
fi
if [ -z "$SERVER_HOST" ] || [ -z "$SERVER_PORT" ]; then
  NETWORK_BOOTSTRAP_REQUIRED=1
fi
case "$TCP_APPLICATION_PORT" in
  *[!0-9]* ) NETWORK_BOOTSTRAP_REQUIRED=1 ;;
esac
if [ "$TCP_APPLICATION_PORT" != "8080" ]; then
  NETWORK_BOOTSTRAP_REQUIRED=1
fi

if [ "$NETWORK_BOOTSTRAP_REQUIRED" = "1" ]; then
  cat > "$BOOTSTRAP_FILE" <<EOF
Railway networking bootstrap is required before Xray can start.

Required control-plane resources:
  Public Domain -> application port 8080
  TCP Proxy     -> application port 8080

Expected Railway runtime variables after networking is configured:
  RAILWAY_PUBLIC_DOMAIN
  RAILWAY_TCP_PROXY_DOMAIN
  RAILWAY_TCP_PROXY_PORT
  RAILWAY_TCP_APPLICATION_PORT=8080

This container intentionally remains alive in bootstrap mode instead of
crash-looping. /health remains available; /ready remains NOT READY.
After Railway networking is created, redeploy/restart the service so the
new Railway-provided variables are injected into the process.
EOF
  chmod 0600 "$BOOTSTRAP_FILE"

  echo "[bootstrap] Railway networking is not ready; Xray startup is deferred."
  echo "[bootstrap] Generate Domain targeting 8080 and create TCP Proxy targeting 8080."
  echo "[bootstrap] Required variables: RAILWAY_PUBLIC_DOMAIN, RAILWAY_TCP_PROXY_DOMAIN, RAILWAY_TCP_PROXY_PORT, RAILWAY_TCP_APPLICATION_PORT=8080"
  echo "[bootstrap] Keeping HTTP gateway alive on 0.0.0.0:$GATEWAY_PORT so /health remains available."
  echo "[bootstrap] After networking is created, redeploy/restart this service."

  export PORT GATEWAY_PORT DATA_DIR XRAY_PORT XRAY_HTTP_PORT XRAY_LISTEN CONFIG XRAY_READY_FILE
  python3 /opt/xray/scripts/health_proxy.py & HEALTH_PID=$!
  cleanup_bootstrap(){ rm -f "$READY_FILE"; kill "${HEALTH_PID:-}" 2>/dev/null || true; wait "${HEALTH_PID:-}" 2>/dev/null || true; }
  trap cleanup_bootstrap INT TERM EXIT
  wait "$HEALTH_PID"
  exit 0
fi

rm -f "$BOOTSTRAP_FILE"

case "$SERVER_PORT" in
  *[!0-9]* ) echo "ERROR: invalid TCP proxy port: $SERVER_PORT" >&2; exit 1 ;;
esac
case "$TCP_APPLICATION_PORT" in
  *[!0-9]* ) echo "ERROR: invalid TCP application port: $TCP_APPLICATION_PORT" >&2; exit 1 ;;
esac
if [ "$TCP_APPLICATION_PORT" != "8080" ]; then
  echo "ERROR: TCP Proxy target/application port must be 8080; got $TCP_APPLICATION_PORT" >&2
  exit 1
fi

PUBLIC_SUBSCRIPTION_URL="https://$PUBLIC_DOMAIN"

if [ -s "$UUID_FILE" ]; then
  UUID=$(tr -d '[:space:]' < "$UUID_FILE")
else
  UUID=$(xray uuid)
  printf '%s\n' "$UUID" > "$UUID_FILE"
fi

if [ -s "$PRIV_FILE" ] && [ -s "$PUB_FILE" ]; then
  PRIVATE_KEY=$(tr -d '[:space:]' < "$PRIV_FILE")
  PUBLIC_KEY=$(tr -d '[:space:]' < "$PUB_FILE")
else
  OUT=$(xray x25519 2>&1)
  PRIVATE_KEY=$(printf '%s\n' "$OUT" | awk '/^PrivateKey[[:space:]]*:/ {sub(/^[^:]*:[[:space:]]*/,"");print;exit} /^Private[[:space:]]+key[[:space:]]*:/ {sub(/^[^:]*:[[:space:]]*/,"");print;exit}')
  PUBLIC_KEY=$(printf '%s\n' "$OUT" | awk '/^Password([[:space:]]*\([^)]*\))?[[:space:]]*:/ {sub(/^[^:]*:[[:space:]]*/,"");print;exit} /^Public[[:space:]]+key[[:space:]]*:/ {sub(/^[^:]*:[[:space:]]*/,"");print;exit}')
  printf '%s\n' "$PRIVATE_KEY" > "$PRIV_FILE"
  printf '%s\n' "$PUBLIC_KEY" > "$PUB_FILE"
fi

if [ -s "$DEC_FILE" ] && [ -s "$ENC_FILE" ]; then
  VLESS_DECRYPTION=$(tr -d '[:space:]' < "$DEC_FILE")
  VLESS_ENCRYPTION=$(tr -d '[:space:]' < "$ENC_FILE")
else
  TMP="$DATA_DIR/.vlessenc.tmp"
  xray vlessenc > "$TMP" 2>&1
  VLESS_DECRYPTION=$(awk '/Authentication:[[:space:]]*ML-KEM-768,[[:space:]]*Post-Quantum/ {m=1;next} m && /"decryption"[[:space:]]*:/ {line=$0;sub(/^.*"decryption"[[:space:]]*:[[:space:]]*"/,"",line);sub(/".*$/,"",line);print line;exit}' "$TMP")
  VLESS_ENCRYPTION=$(awk '/Authentication:[[:space:]]*ML-KEM-768,[[:space:]]*Post-Quantum/ {m=1;next} m && /"encryption"[[:space:]]*:/ {line=$0;sub(/^.*"encryption"[[:space:]]*:[[:space:]]*"/,"",line);sub(/".*$/,"",line);print line;exit}' "$TMP")
  rm -f "$TMP"
  printf '%s\n' "$VLESS_DECRYPTION" > "$DEC_FILE"
  printf '%s\n' "$VLESS_ENCRYPTION" > "$ENC_FILE"
fi

if [ -s "$TOKEN_FILE" ]; then
  SUBSCRIPTION_TOKEN=$(tr -d '[:space:]' < "$TOKEN_FILE")
else
  SUBSCRIPTION_TOKEN=$(python3 -c 'import secrets; print(secrets.token_urlsafe(32))')
  printf '%s\n' "$SUBSCRIPTION_TOKEN" > "$TOKEN_FILE"
fi

export PORT GATEWAY_PORT DATA_DIR XRAY_PORT XRAY_HTTP_PORT XRAY_LISTEN CONFIG REALITY_TARGET REALITY_SNI REALITY_FINGERPRINT XHTTP_PATH XHTTP_MODE SHORT_ID REALITY_SNI_LIMIT PUBLIC_DOMAIN UUID PRIVATE_KEY PUBLIC_KEY VLESS_DECRYPTION VLESS_ENCRYPTION SERVER_HOST SERVER_PORT TCP_APPLICATION_PORT SUBSCRIPTION_TOKEN XRAY_READY_FILE

printf '%s\n' \
  "[startup] Railway public domain: $PUBLIC_DOMAIN" \
  "[startup] TCP proxy: $SERVER_HOST:$SERVER_PORT" \
  "[startup] TCP application port: $TCP_APPLICATION_PORT" \
  "[startup] Gateway: 0.0.0.0:$GATEWAY_PORT" \
  "[startup] Xray REALITY: $XRAY_LISTEN:$XRAY_PORT" \
  "[startup] Xray HTTPS/XHTTP: $XRAY_LISTEN:$XRAY_HTTP_PORT"

python3 /opt/xray/scripts/generate.py
printf '%s/sub/%s\n' "${PUBLIC_SUBSCRIPTION_URL%/}" "$SUBSCRIPTION_TOKEN" > "$URL_FILE"
chmod 0600 "$URL_FILE"

python3 /opt/xray/scripts/health_proxy.py & HEALTH_PID=$!
cleanup(){
  rm -f "$READY_FILE"
  kill "${XRAY_PID:-}" 2>/dev/null || true
  kill "${HEALTH_PID:-}" 2>/dev/null || true
  wait "${XRAY_PID:-}" 2>/dev/null || true
  wait "${HEALTH_PID:-}" 2>/dev/null || true
}
trap cleanup INT TERM EXIT

xray run -test -config "$CONFIG"
xray run -config "$CONFIG" & XRAY_PID=$!

for _ in $(seq 1 60); do
  python3 - <<'PY' && break
import socket
s=socket.create_connection(('127.0.0.1',10087),1)
s.close()
PY
  sleep 1
done

touch "$READY_FILE"
wait "$XRAY_PID"
