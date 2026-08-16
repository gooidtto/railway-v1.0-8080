#!/bin/sh
set -eu

DATA_DIR="${RAILWAY_VOLUME_MOUNT_PATH:-${DATA_DIR:-/data}}"
export DATA_DIR
mkdir -p "$DATA_DIR"

# Four-stage runtime pipeline:
#   1. runtime-discovery
#   2. xray-config-generator
#   3. subscription-generator
#   4. gateway-router
#
# Railway-generated domains, ports and instance identifiers are never stored
# in source code. They are rediscovered on every process start.
python3 /opt/xray/scripts/runtime_discovery.py
python3 /opt/xray/scripts/xray_config_generator.py
python3 /opt/xray/scripts/subscription_generator.py

CONFIG="${XRAY_CONFIG:-/etc/xray/config.json}"
READY_FILE="$DATA_DIR/.xray-ready"
rm -f "$READY_FILE"

xray run -test -config "$CONFIG"
xray run -config "$CONFIG" &
XRAY_PID=$!

cleanup() {
  rm -f "$READY_FILE"
  kill "$XRAY_PID" 2>/dev/null || true
  kill "${GATEWAY_PID:-}" 2>/dev/null || true
  wait "$XRAY_PID" 2>/dev/null || true
  wait "${GATEWAY_PID:-}" 2>/dev/null || true
}
trap cleanup INT TERM EXIT

# Wait for all four local inbound listeners before publishing readiness.
for _ in $(seq 1 60); do
  if python3 - <<'PY'
import socket
ports = (10085, 10086, 10087, 10088)
for port in ports:
    s = socket.create_connection(('127.0.0.1', port), 1)
    s.close()
PY
  then
    break
  fi
  sleep 1
done

python3 - <<'PY'
import socket
for port in (10085, 10086, 10087, 10088):
    s = socket.create_connection(('127.0.0.1', port), 1)
    s.close()
PY

touch "$READY_FILE"
python3 /opt/xray/scripts/gateway_router.py &
GATEWAY_PID=$!

wait "$GATEWAY_PID"
