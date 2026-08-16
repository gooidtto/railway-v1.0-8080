#!/usr/bin/env python3
import json, os, socket
from pathlib import Path

DATA_DIR = Path(os.getenv("DATA_DIR", "/data"))
RUNTIME_FILE = DATA_DIR / "runtime.json"
RESERVED = {8080}
NAMES = ("xhttp_reality", "xhttp_tls")

def allocate():
    sockets, ports = [], {}
    try:
        for name in NAMES:
            while True:
                s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
                s.bind(("127.0.0.1", 0))
                port = s.getsockname()[1]
                if port not in RESERVED and port not in ports.values():
                    ports[name] = port; sockets.append(s); break
                s.close()
        return ports
    finally:
        for s in sockets: s.close()

def main():
    runtime = json.loads(RUNTIME_FILE.read_text(encoding="utf-8"))
    ports = allocate()
    listeners = runtime.setdefault("listeners", {})
    listeners["gateway"] = int(runtime["railway"]["port"])
    for name, port in ports.items(): listeners[name] = port
    listeners.pop("vision_reality", None); listeners.pop("grpc_reality", None)
    runtime["listener_policy"] = {"gateway":"fixed","xray":"dynamic-localhost","address":"127.0.0.1","per_start":True,"transport":"xhttp-only-stable-baseline"}
    tmp = RUNTIME_FILE.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(runtime, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    os.chmod(tmp, 0o600); os.replace(tmp, RUNTIME_FILE)
    print("[port-allocator] gateway=%s" % listeners["gateway"])
    for name in NAMES: print("[port-allocator] %s=127.0.0.1:%s" % (name, listeners[name]))
if __name__ == "__main__": main()
