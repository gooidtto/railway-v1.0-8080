#!/bin/sh
set -eu

DATA_DIR="${RAILWAY_VOLUME_MOUNT_PATH:-${DATA_DIR:-/data}}"
export DATA_DIR
mkdir -p "$DATA_DIR"

# Runtime pipeline:
#   1. discover Railway networking
#   2. allocate fresh private Xray listener ports
#   3. generate Xray + runtime manifest
#   4. generate subscription from the same manifest
#   5. start Gateway from the same manifest
python3 /opt/xray/scripts/runtime_discovery.py
python3 /opt/xray/scripts/port_allocator.py
python3 /opt/xray/scripts/xray_config_generator.py
python3 /opt/xray/scripts/subscription_generator.py

CONFIG="${XRAY_CONFIG:-/etc/xray/config.json}"
READY_FILE="$DATA_DIR/.xray-ready"
rm -f "$READY_FILE"

set -- $(python3 - <<'PY'
import json
import os
from pathlib import Path
root = Path(os.getenv('DATA_DIR', '/data'))
p = json.loads((root / 'runtime.json').read_text())['listeners']
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

# Wait until every dynamically allocated Xray listener is accepting local TCP.
READY=0
for _ in $(seq 1 60); do
  if python3 - "$XRAY_XHTTP_REALITY_PORT" "$XRAY_XHTTP_TLS_PORT" "$XRAY_VISION_REALITY_PORT" "$XRAY_GRPC_REALITY_PORT" <<'PY'
import socket, sys
for value in sys.argv[1:]:
    s = socket.create_connection(('127.0.0.1', int(value)), 1)
    s.close()
PY
  then
    READY=1
    break
  fi
  sleep 1
done

if [ "$READY" -ne 1 ]; then
  echo "ERROR: Xray did not bind all dynamic listeners" >&2
  exit 1
fi

python3 /opt/xray/scripts/gateway_router.py &
GATEWAY_PID=$!

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
