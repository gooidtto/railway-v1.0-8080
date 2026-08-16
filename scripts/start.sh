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

# Read the generated local listener contract instead of duplicating the
# listener numbers in the startup orchestrator.
set -- $(python3 - <<'PY'
import json
from pathlib import Path
p = json.loads(Path('/data/runtime.json').read_text())['listeners']
print(p['xhttp_reality'], p['xhttp_tls'], p['vision_reality'], p['grpc_reality'], p['gateway'])
PY
)
XRAY_XHTTP_REALITY_PORT="$1"
XRAY_XHTTP_TLS_PORT="$2"
XRAY_VISION_REALITY_PORT="$3"
XRAY_GRPC_REALITY_PORT="$4"
GATEWAY_PORT="$5"

xray run -test -config "$CONFIG"
xray run -config "$CONFIG" &
XRAY_PID=$!

cleanup() {
  rm -f "$READY_FILE"
  kill "${GATEWAY_PID:-}" 2>/dev/null || true
  kill "$XRAY_PID" 2>/dev/null || true
  wait "${GATEWAY_PID:-}" 2>/dev/null || true
  wait "$XRAY_PID" 2>/dev/null || true
}
trap cleanup INT TERM EXIT

# Wait for all four generated Xray listeners before starting the Gateway.
for _ in $(seq 1 60); do
  if python3 - "$XRAY_XHTTP_REALITY_PORT" "$XRAY_XHTTP_TLS_PORT" "$XRAY_VISION_REALITY_PORT" "$XRAY_GRPC_REALITY_PORT" <<'PY'
import socket
import sys
for value in sys.argv[1:]:
    s = socket.create_connection(('127.0.0.1', int(value)), 1)
    s.close()
PY
  then
    break
  fi
  sleep 1
done

python3 - "$XRAY_XHTTP_REALITY_PORT" "$XRAY_XHTTP_TLS_PORT" "$XRAY_VISION_REALITY_PORT" "$XRAY_GRPC_REALITY_PORT" <<'PY'
import socket
import sys
for value in sys.argv[1:]:
    s = socket.create_connection(('127.0.0.1', int(value)), 1)
    s.close()
PY

python3 /opt/xray/scripts/gateway_router.py &
GATEWAY_PID=$!

# Railway health checks use the generated Gateway port. Do not publish
# readiness until the Gateway binds successfully.
for _ in $(seq 1 30); do
  if python3 - "$GATEWAY_PORT" <<'PY'
import socket, sys
s = socket.create_connection(('127.0.0.1', int(sys.argv[1])), 1)
s.close()
PY
  then
    touch "$READY_FILE"
    break
  fi
  sleep 1
done

if [ ! -f "$READY_FILE" ]; then
  echo "ERROR: Gateway did not bind to PORT=$GATEWAY_PORT" >&2
  exit 1
fi

wait "$GATEWAY_PID"
