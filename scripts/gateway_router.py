#!/usr/bin/env python3
import json, os, select, socket, threading
from pathlib import Path
from urllib.parse import urlsplit
DATA_DIR=Path(os.getenv("DATA_DIR","/data")); RUNTIME_FILE=DATA_DIR/"runtime.json"; MANIFEST_FILE=DATA_DIR/"xray-manifest.json"; SITE_DIR=Path(os.getenv("SITE_DIR","/opt/xray/site")).resolve(); SUB_FILE=DATA_DIR/"subscription.txt"; TOKEN_FILE=DATA_DIR/"subscription_token.txt"; READY_FILE=DATA_DIR/".xray-ready"
def load(path,default=None):
    try:return json.loads(path.read_text(encoding="utf-8"))
    except (OSError,ValueError):return default
def log(m):print("[gateway-router] "+m,flush=True)
def tune(s):
    for level,opt,val in ((socket.IPPROTO_TCP,socket.TCP_NODELAY,1),(socket.SOL_SOCKET,socket.SO_KEEPALIVE,1)):
        try:s.setsockopt(level,opt,val)
        except OSError:pass
    for opt,val in ((getattr(socket,"TCP_KEEPIDLE",None),60),(getattr(socket,"TCP_KEEPINTVL",None),20),(getattr(socket,"TCP_KEEPCNT",None),3)):
        if opt is not None:
            try:s.setsockopt(socket.IPPROTO_TCP,opt,val)
            except OSError:pass
def response(status,ctype,body,head=False):
    if isinstance(body,str):body=body.encode()
    reason={200:"OK",404:"Not Found",405:"Method Not Allowed",503:"Service Unavailable"}.get(status,"OK")
    h=("HTTP/1.1 %s %s\r\nContent-Type: %s\r\nContent-Length: %d\r\nConnection: close\r\nCache-Control: no-store\r\nX-Content-Type-Options: nosniff\r\n\r\n")%(status,reason,ctype,len(body));return h.encode() if head else h.encode()+body
def strip_proxy(data):
    if data.startswith(b"PROXY "):
        end=data.find(b"\r\n")
        if end>=0:return data[end+2:]
    sig=b"\r\n\r\n\x00\r\nQUIT\n"
    if data.startswith(sig) and len(data)>=16:
        total=16+int.from_bytes(data[14:16],"big")
        if len(data)>=total:return data[total:]
    return data
def classify(data):
    raw=strip_proxy(data)
    if raw[:1]==b"\x16" and len(raw)>=3 and raw[1]==3:return raw,"tls"
    if b"\r\n\r\n" in raw or b"\n\n" in raw:return raw,"http"
    methods=(b"GET ",b"HEAD ",b"POST ",b"PUT ",b"DELETE ",b"OPTIONS ",b"PATCH ",b"CONNECT ")
    if raw.startswith(methods):return raw,"http"
    return raw,"tcp"
def recv_initial(s,timeout=10):
    s.settimeout(timeout);data=bytearray()
    while len(data)<16384:
        chunk=s.recv(min(4096,16384-len(data)))
        if not chunk:break
        data.extend(chunk);raw,kind=classify(bytes(data))
        if raw and kind in ("tls","http","tcp"):return raw,kind
    return classify(bytes(data))
def relay(a,b,initial=b""):
    tune(a);tune(b);a.settimeout(None);b.settimeout(None)
    if initial:b.sendall(initial)
    c2s,s2c=len(initial),0
    while True:
        readable,_,bad=select.select((a,b),(),(a,b),300)
        if bad or not readable:return c2s,s2c
        for src in readable:
            dst=b if src is a else a;chunk=src.recv(65536)
            if not chunk:return c2s,s2c
            dst.sendall(chunk)
            if src is a:c2s+=len(chunk)
            else:s2c+=len(chunk)
def connect(port):
    s=socket.create_connection(("127.0.0.1",int(port)),timeout=10);tune(s);return s
def parse_http(data):
    try:
        method,target,version=data.split(b"\r\n",1)[0].decode("ascii").split(" ",2)
        if not version.startswith("HTTP/"):return None
        return method,urlsplit(target).path or "/"
    except (UnicodeDecodeError,ValueError):return None
def website(c,method,path):
    if path=="/health":c.sendall(response(200,"text/plain; charset=utf-8","OK\n",method=="HEAD"));return True
    if path=="/ready":
        ok=READY_FILE.exists();c.sendall(response(200 if ok else 503,"text/plain; charset=utf-8","READY\n" if ok else "NOT READY\n",method=="HEAD"));return True
    if path.startswith("/sub/"):
        token=TOKEN_FILE.read_text().strip() if TOKEN_FILE.is_file() else ""
        if token and path=="/sub/"+token and SUB_FILE.is_file():c.sendall(response(200,"text/plain; charset=utf-8",SUB_FILE.read_bytes(),method=="HEAD"))
        else:c.sendall(response(404,"text/plain; charset=utf-8","Not Found\n",method=="HEAD"))
        return True
    if path=="/sub":c.sendall(response(404,"text/plain; charset=utf-8","Not Found\n",method=="HEAD"));return True
    if method not in {"GET","HEAD"}:c.sendall(response(405,"text/plain; charset=utf-8","Method Not Allowed\n"));return True
    rel="index.html" if path=="/" else path.lstrip("/");target=(SITE_DIR/rel).resolve()
    if SITE_DIR not in target.parents and target!=SITE_DIR or not target.is_file():c.sendall(response(404,"text/plain; charset=utf-8","Not Found\n",method=="HEAD"));return True
    body=target.read_bytes();types={".html":"text/html; charset=utf-8",".css":"text/css; charset=utf-8",".js":"application/javascript; charset=utf-8",".json":"application/json; charset=utf-8",".svg":"image/svg+xml",".png":"image/png",".jpg":"image/jpeg",".jpeg":"image/jpeg"};c.sendall(response(200,types.get(target.suffix.lower(),"application/octet-stream"),body,method=="HEAD"));return True
def handle(c,addr):
    up=None;peer="%s:%s"%addr[:2];log("ACCEPT peer=%s ready=%s"%(peer,READY_FILE.exists()))
    try:
        initial,kind=recv_initial(c)
        if not initial:log("CLOSE peer=%s reason=no-initial-data"%peer);return
        ports=load(RUNTIME_FILE,{}).get("listeners",{});reality=ports.get("xhttp_reality");xhttp=ports.get("xhttp_tls")
        if not reality or not xhttp:log("ERROR peer=%s missing Xray listener ports"%peer);return
        log("CLASSIFY peer=%s kind=%s bytes=%d head=%s"%(peer,kind,len(initial),initial[:12].hex()))
        if kind=="tls":
            up=connect(reality);log("UPSTREAM_CONNECTED peer=%s target=127.0.0.1:%s kind=tls-reality"%(peer,reality));a,b=relay(c,up,initial);log("RELAY_END peer=%s kind=tls-reality c2s=%d s2c=%d"%(peer,a,b));return
        parsed=parse_http(initial)
        if parsed:
            method,path=parsed;log("HTTP peer=%s method=%s path=%s"%(peer,method,path));xpath=load(MANIFEST_FILE,{}).get("xhttp_path","/xhttp")
            if path!=xpath and not path.startswith(xpath+"/"):website(c,method,path);return
            up=connect(xhttp);log("UPSTREAM_CONNECTED peer=%s target=127.0.0.1:%s kind=http-xhttp"%(peer,xhttp));a,b=relay(c,up,initial);log("RELAY_END peer=%s kind=http-xhttp c2s=%d s2c=%d"%(peer,a,b));return
        log("REJECT peer=%s kind=%s"%(peer,kind))
    except (OSError,TimeoutError) as exc:log("ERROR peer=%s type=%s detail=%s"%(peer,type(exc).__name__,exc))
    finally:
        if up:
            try:up.close()
            except OSError:pass
        try:c.close()
        except OSError:pass
def main():
    runtime=load(RUNTIME_FILE,{}) or {};port=int(runtime.get("listeners",{}).get("gateway",os.getenv("PORT","8080")))
    with socket.socket(socket.AF_INET,socket.SOCK_STREAM) as s:
        s.setsockopt(socket.SOL_SOCKET,socket.SO_REUSEADDR,1);s.bind(("0.0.0.0",port));s.listen(256);log("LISTEN 0.0.0.0:%d"%port)
        while True:
            c,addr=s.accept();threading.Thread(target=handle,args=(c,addr),daemon=True).start()
if __name__=="__main__":main()
