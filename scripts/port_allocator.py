#!/usr/bin/env python3
import json,os,socket
from pathlib import Path
DATA_DIR=Path(os.getenv('DATA_DIR','/data')); RUNTIME_FILE=DATA_DIR/'runtime.json'
def allocate():
    sockets=[]; ports={}
    try:
        for name in ('xhttp_reality','xhttp_tls'):
            s=socket.socket(); s.setsockopt(socket.SOL_SOCKET,socket.SO_REUSEADDR,1); s.bind(('127.0.0.1',0)); ports[name]=s.getsockname()[1]; sockets.append(s)
        return ports
    finally:
        for s in sockets: s.close()
def main():
    runtime=json.loads(RUNTIME_FILE.read_text()); ports=allocate(); runtime.setdefault('listeners',{}); runtime['listeners']['gateway']=int(runtime['railway']['port']); runtime['listeners'].update(ports); runtime['listener_policy']={'gateway':'fixed','xray':'dynamic-localhost','address':'127.0.0.1','per_start':True}
    for stale in ('vision_reality','grpc_reality'): runtime['listeners'].pop(stale,None)
    tmp=RUNTIME_FILE.with_suffix('.tmp'); tmp.write_text(json.dumps(runtime,indent=2,sort_keys=True)+'\n'); os.chmod(tmp,0o600); os.replace(tmp,RUNTIME_FILE)
    print('[port-allocator] gateway=%s'%runtime['listeners']['gateway']); print('[port-allocator] xhttp_reality=127.0.0.1:%s'%ports['xhttp_reality']); print('[port-allocator] xhttp_tls=127.0.0.1:%s'%ports['xhttp_tls'])
if __name__=='__main__': main()
