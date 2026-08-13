#!/bin/sh
set -eu
DATA_DIR="${RAILWAY_VOLUME_MOUNT_PATH:-${DATA_DIR:-/data}}"
GATEWAY_PORT="${GATEWAY_PORT:-${PORT:-8080}}"
PORT="$GATEWAY_PORT" XRAY_PORT="${XRAY_PORT:-10087}" XRAY_HTTP_PORT="${XRAY_HTTP_PORT:-10086}" XRAY_LISTEN="${XRAY_LISTEN:-127.0.0.1}"
CONFIG="${XRAY_CONFIG:-/etc/xray/config.json}"
REALITY_TARGET="${REALITY_TARGET:-www.cloudflare.com:443}" REALITY_SNI="${REALITY_SNI:-${REALITY_TARGET%%:*}}" REALITY_FINGERPRINT="${REALITY_FINGERPRINT:-chrome}" XHTTP_PATH="${XHTTP_PATH:-/xhttp}" XHTTP_MODE="${XHTTP_MODE:-auto}" SHORT_ID="${SHORT_ID:-50175c035ee132}"
SERVER_HOST="${SERVER_HOST:-${XRAY_TCP_PROXY_HOST:-${RAILWAY_TCP_PROXY_DOMAIN:-}}}" SERVER_PORT="${SERVER_PORT:-${XRAY_TCP_PROXY_PORT:-${RAILWAY_TCP_PROXY_PORT:-}}}"
READY_FILE="$DATA_DIR/.xray-ready"; TOKEN_FILE="$DATA_DIR/subscription_token.txt"; UUID_FILE="$DATA_DIR/uuid.txt"; PRIV_FILE="$DATA_DIR/reality_private_key.txt"; PUB_FILE="$DATA_DIR/reality_public_key.txt"; DEC_FILE="$DATA_DIR/vless_decryption.txt"; ENC_FILE="$DATA_DIR/vless_encryption.txt"
mkdir -p "$DATA_DIR" "$(dirname "$CONFIG")"; chmod 0700 "$DATA_DIR"; rm -f "$READY_FILE"
if [ -s "$UUID_FILE" ]; then UUID=$(tr -d '[:space:]' < "$UUID_FILE"); else UUID=$(xray uuid); printf '%s\n' "$UUID" > "$UUID_FILE"; fi
if [ -s "$PRIV_FILE" ] && [ -s "$PUB_FILE" ]; then PRIVATE_KEY=$(tr -d '[:space:]' < "$PRIV_FILE"); PUBLIC_KEY=$(tr -d '[:space:]' < "$PUB_FILE"); else OUT=$(xray x25519 2>&1); PRIVATE_KEY=$(printf '%s\n' "$OUT" | awk '/^PrivateKey[[:space:]]*:/ {sub(/^[^:]*:[[:space:]]*/,"");print;exit} /^Private[[:space:]]+key[[:space:]]*:/ {sub(/^[^:]*:[[:space:]]*/,"");print;exit}'); PUBLIC_KEY=$(printf '%s\n' "$OUT" | awk '/^Password([[:space:]]*\([^)]*\))?[[:space:]]*:/ {sub(/^[^:]*:[[:space:]]*/,"");print;exit} /^Public[[:space:]]+key[[:space:]]*:/ {sub(/^[^:]*:[[:space:]]*/,"");print;exit}'); printf '%s\n' "$PRIVATE_KEY" > "$PRIV_FILE"; printf '%s\n' "$PUBLIC_KEY" > "$PUB_FILE"; fi
if [ -s "$DEC_FILE" ] && [ -s "$ENC_FILE" ]; then VLESS_DECRYPTION=$(tr -d '[:space:]' < "$DEC_FILE"); VLESS_ENCRYPTION=$(tr -d '[:space:]' < "$ENC_FILE"); else TMP="$DATA_DIR/.vlessenc.tmp"; xray vlessenc > "$TMP" 2>&1; VLESS_DECRYPTION=$(awk '/Authentication:[[:space:]]*ML-KEM-768,[[:space:]]*Post-Quantum/ {m=1;next} m && /"decryption"[[:space:]]*:/ {line=$0;sub(/^.*"decryption"[[:space:]]*:[[:space:]]*"/,"",line);sub(/".*$/,"",line);print line;exit}' "$TMP"); VLESS_ENCRYPTION=$(awk '/Authentication:[[:space:]]*ML-KEM-768,[[:space:]]*Post-Quantum/ {m=1;next} m && /"encryption"[[:space:]]*:/ {line=$0;sub(/^.*"encryption"[[:space:]]*:[[:space:]]*"/,"",line);sub(/".*$/,"",line);print line;exit}' "$TMP"); rm -f "$TMP"; printf '%s\n' "$VLESS_DECRYPTION" > "$DEC_FILE"; printf '%s\n' "$VLESS_ENCRYPTION" > "$ENC_FILE"; fi
if [ -s "$TOKEN_FILE" ]; then SUBSCRIPTION_TOKEN=$(tr -d '[:space:]' < "$TOKEN_FILE"); else SUBSCRIPTION_TOKEN=$(python3 -c 'import secrets; print(secrets.token_urlsafe(32))'); printf '%s\n' "$SUBSCRIPTION_TOKEN" > "$TOKEN_FILE"; fi
export PORT GATEWAY_PORT DATA_DIR XRAY_PORT XRAY_HTTP_PORT XRAY_LISTEN CONFIG REALITY_TARGET REALITY_SNI REALITY_FINGERPRINT XHTTP_PATH XHTTP_MODE SHORT_ID UUID PRIVATE_KEY PUBLIC_KEY VLESS_DECRYPTION VLESS_ENCRYPTION SERVER_HOST SERVER_PORT SUBSCRIPTION_TOKEN XRAY_READY_FILE="$READY_FILE"
python3 /opt/xray/scripts/generate.py
python3 /opt/xray/scripts/apply_reality_sni_pool.py
python3 /opt/xray/scripts/health_proxy.py & HEALTH_PID=$!
cleanup(){ rm -f "$READY_FILE"; kill "${XRAY_PID:-}" 2>/dev/null || true; kill "${HEALTH_PID:-}" 2>/dev/null || true; wait "${XRAY_PID:-}" 2>/dev/null || true; wait "${HEALTH_PID:-}" 2>/dev/null || true; }; trap cleanup INT TERM EXIT
xray run -test -config "$CONFIG"
xray run -config "$CONFIG" & XRAY_PID=$!
for _ in $(seq 1 60); do python3 - <<'PY' && break
import socket
s=socket.create_connection(('127.0.0.1',10087),1); s.close()
PY
sleep 1
done
touch "$READY_FILE"
wait "$XRAY_PID"
