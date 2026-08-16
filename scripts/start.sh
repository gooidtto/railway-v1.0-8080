#!/bin/sh
set -eu
DATA_DIR="${RAILWAY_VOLUME_MOUNT_PATH:-${DATA_DIR:-/data}}";export DATA_DIR;mkdir -p "$DATA_DIR"
python3 /opt/xray/scripts/runtime_discovery.py
python3 /opt/xray/scripts/port_allocator.py
python3 /opt/xray/scripts/xray_config_generator.py
python3 /opt/xray/scripts/subscription_generator.py
CONFIG="${XRAY_CONFIG:-/etc/xray/config.json}";READY_FILE="$DATA_DIR/.xray-ready";rm -f "$READY_FILE"
set -- $(python3 - <<'PY'
import json,os
from pathlib import Path
p=json.loads((Path(os.getenv("DATA_DIR","/data"))/"runtime.json").read_text())["listeners"]
print(p["xhttp_reality"],p["xhttp_tls"],p["gateway"])
PY
)
REALITY_PORT="$1";XHTTP_PORT="$2";GATEWAY_PORT="$3"
cleanup(){ rm -f "$READY_FILE";kill "${GATEWAY_PID:-}" 2>/dev/null||true;kill "${XRAY_PID:-}" 2>/dev/null||true;wait "${GATEWAY_PID:-}" 2>/dev/null||true;wait "${XRAY_PID:-}" 2>/dev/null||true; }
trap cleanup INT TERM EXIT
xray run -test -config "$CONFIG"
xray run -config "$CONFIG" & XRAY_PID=$!
READY=0
for _ in $(seq 1 60); do
  if python3 - "$REALITY_PORT" "$XHTTP_PORT" <<'PY'
import socket,sys
for p in sys.argv[1:]:
    s=socket.create_connection(("127.0.0.1",int(p)),1);s.close()
PY
  then READY=1;break;fi
  sleep 1
done
[ "$READY" -eq 1 ] || { echo "ERROR: Xray did not bind both stable listeners" >&2;exit 1; }
echo "[startup] Xray READY: reality=$REALITY_PORT xhttp=$XHTTP_PORT"
python3 /opt/xray/scripts/gateway_router.py & GATEWAY_PID=$!
GATEWAY_READY=0
for _ in $(seq 1 30); do
  if python3 - "$GATEWAY_PORT" <<'PY'
import socket,sys
s=socket.create_connection(("127.0.0.1",int(sys.argv[1])),1);s.close()
PY
  then GATEWAY_READY=1;break;fi
  sleep 1
done
[ "$GATEWAY_READY" -eq 1 ] || { echo "ERROR: Gateway did not bind PORT=$GATEWAY_PORT" >&2;exit 1; }
python3 - <<'PY'
import json,os,socket
from pathlib import Path
root=Path(os.getenv("DATA_DIR","/data"));runtime=json.loads((root/"runtime.json").read_text());port=int(runtime["listeners"]["gateway"]);token=(root/"subscription_token.txt").read_text().strip();expected=(root/"subscription.txt").read_bytes().strip();path="/sub/"+token;req=("GET %s HTTP/1.1\r\nHost: localhost\r\nConnection: close\r\n\r\n"%path).encode()
with socket.create_connection(("127.0.0.1",port),timeout=5) as s:
    s.sendall(req);raw=b""
    while True:
        c=s.recv(65536)
        if not c:break
        raw+=c
head,_,body=raw.partition(b"\r\n\r\n");status=head.split(b"\r\n",1)[0] if head else b""
if not status.startswith(b"HTTP/1.1 200 "):raise SystemExit("[startup] ERROR: local subscription HTTP check failed: %s"%status.decode("latin1","replace"))
if body.strip()!=expected:raise SystemExit("[startup] ERROR: subscription body mismatch")
print("[startup] local subscription check=OK bytes=%d path=%s"%(len(body.strip()),path),flush=True)
PY
touch "$READY_FILE";echo "[startup] READY: gateway=$GATEWAY_PORT subscription=OK";wait "$GATEWAY_PID"
