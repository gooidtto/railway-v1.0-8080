#!/usr/bin/env python3
import json
import os
import select
import socket
import threading
from pathlib import Path
from urllib.parse import urlsplit

DATA_DIR = Path(os.getenv('DATA_DIR', '/data'))
RUNTIME_FILE = DATA_DIR / 'runtime.json'
MANIFEST_FILE = DATA_DIR / 'xray-manifest.json'
SITE_DIR = Path(os.getenv('SITE_DIR', '/opt/xray/site')).resolve()
SUB_FILE = DATA_DIR / 'subscription.txt'
TOKEN_FILE = DATA_DIR / 'subscription_token.txt'
DEBUG = os.getenv('GATEWAY_DEBUG', '1').lower() not in {'0', 'false', 'no'}


def load(path, default=None):
    try:
        return json.loads(path.read_text(encoding='utf-8'))
    except (OSError, ValueError):
        return default


def log(message):
    if DEBUG:
        print('[gateway-router] %s' % message, flush=True)


def tune(s):
    for level, opt, val in ((socket.IPPROTO_TCP, socket.TCP_NODELAY, 1),
                            (socket.SOL_SOCKET, socket.SO_KEEPALIVE, 1)):
        try: s.setsockopt(level, opt, val)
        except OSError: pass
    for opt, val in ((socket.TCP_KEEPIDLE, 60), (socket.TCP_KEEPINTVL, 20), (socket.TCP_KEEPCNT, 3)):
        try: s.setsockopt(socket.IPPROTO_TCP, opt, val)
        except OSError: pass


def http_response(status, ctype, body, head=False):
    if isinstance(body, str): body = body.encode()
    reason = {200:'OK',404:'Not Found',405:'Method Not Allowed',503:'Service Unavailable'}.get(status, 'OK')
    h = ('HTTP/1.1 %s %s\r\nContent-Type: %s\r\nContent-Length: %d\r\nConnection: keep-alive\r\nKeep-Alive: timeout=30, max=1000\r\nCache-Control: no-store\r\nX-Content-Type-Options: nosniff\r\n\r\n') % (status, reason, ctype, len(body))
    return h.encode() if head else h.encode() + body


def parse_http(data):
    try:
        head = data.split(b'\r\n\r\n', 1)[0]
        first = head.split(b'\r\n', 1)[0].decode('ascii')
        parts = first.split(' ', 2)
        if len(parts) != 3 or not parts[2].startswith('HTTP/'): return None
        target = urlsplit(parts[1])
        return parts[0], target.path or '/', target.netloc
    except (UnicodeDecodeError, ValueError):
        return None


def recv_initial(s, timeout=8):
    s.settimeout(timeout)
    data = bytearray()
    while len(data) < 131072:
        chunk = s.recv(min(8192, 131072-len(data)))
        if not chunk: break
        data.extend(chunk)
        raw = bytes(data)
        if b'\r\n\r\n' in raw: return raw
        if len(raw) >= 5 and raw[0] == 0x16 and raw[1] == 0x03: return raw
        if len(raw) >= 8 and raw[0] != 0x16 and not raw.startswith((b'GET ',b'POST ',b'HEAD ',b'PUT ',b'OPTIONS ',b'PATCH ',b'DELETE ',b'CONNECT ')): return raw
    return bytes(data)


def relay(a, b, initial=b''):
    tune(a); tune(b); a.settimeout(None); b.settimeout(None)
    if initial: b.sendall(initial)
    log('upstream-connected peer=%s upstream=%s initial=%d' % (a.getpeername(), b.getpeername(), len(initial)))
    alive = [True, True]
    while any(alive):
        readable, _, _ = select.select((a,b), (), (), 120)
        if not readable:
            log('relay-idle-timeout'); break
        for src in readable:
            dst = b if src is a else a
            try: chunk = src.recv(65536)
            except OSError: chunk = b''
            if not chunk:
                idx = 0 if src is a else 1
                alive[idx] = False
                try: dst.shutdown(socket.SHUT_WR)
                except OSError: pass
                continue
            dst.sendall(chunk)


def connect(port):
    s = socket.create_connection(('127.0.0.1', int(port)), timeout=8)
    tune(s); return s


def website(c, method, path):
    if path == '/health': c.sendall(http_response(200,'text/plain; charset=utf-8','OK\n',method=='HEAD')); return True
    if path.startswith('/sub/'):
        token = TOKEN_FILE.read_text().strip() if TOKEN_FILE.is_file() else ''
        if token and path == '/sub/'+token and SUB_FILE.is_file():
            body = SUB_FILE.read_bytes(); log('http subscription served bytes=%d' % len(body)); c.sendall(http_response(200,'text/plain; charset=utf-8',body,method=='HEAD'))
        else: c.sendall(http_response(404,'text/plain; charset=utf-8','Not Found\n',method=='HEAD'))
        return True
    if path == '/sub': c.sendall(http_response(404,'text/plain; charset=utf-8','Not Found\n',method=='HEAD')); return True
    if method not in {'GET','HEAD'}: c.sendall(http_response(405,'text/plain; charset=utf-8','Method Not Allowed\n')); return True
    rel = 'index.html' if path == '/' else path.lstrip('/')
    target = (SITE_DIR / rel).resolve()
    if (SITE_DIR not in target.parents and target != SITE_DIR) or not target.is_file():
        c.sendall(http_response(404,'text/plain; charset=utf-8','Not Found\n',method=='HEAD')); return True
    body = target.read_bytes()
    types = {'.html':'text/html; charset=utf-8','.css':'text/css; charset=utf-8','.js':'application/javascript; charset=utf-8','.json':'application/json','.svg':'image/svg+xml','.png':'image/png','.jpg':'image/jpeg','.jpeg':'image/jpeg'}
    c.sendall(http_response(200,types.get(target.suffix.lower(),'application/octet-stream'),body,method=='HEAD')); return True


def handle(c, addr):
    upstream = None
    try:
        log('ACCEPT peer=%s:%s' % addr[:2])
        initial = recv_initial(c)
        if not initial: log('CLOSE empty'); return
        runtime = load(RUNTIME_FILE,{})
        manifest = load(MANIFEST_FILE,{})
        ports = runtime.get('listeners',{})
        reality_port = ports.get('xhttp_reality')
        http_port = ports.get('xhttp_tls')
        if initial[:1] == b'\x16' and len(initial) >= 3:
            log('CLASSIFY peer=%s:%s kind=tls bytes=%d -> xhttp-reality:%s' % (addr[0],addr[1],len(initial),reality_port))
            upstream = connect(reality_port)
            relay(c, upstream, initial)
            return
        parsed = parse_http(initial)
        if parsed:
            method, path, host = parsed
            log('CLASSIFY peer=%s:%s kind=http host=%s path=%s' % (addr[0],addr[1],host or '-',path))
            xhttp_path = manifest.get('xhttp_path','/xhttp')
            if path == '/health' or path.startswith('/sub/') or path == '/sub' or path == '/ready' or path == '/':
                website(c, method, path); return
            if path == xhttp_path or path.startswith(xhttp_path + '/'):
                upstream = connect(http_port)
                relay(c, upstream, initial)
                return
            website(c, method, path); return
        log('REJECT unknown first=0x%02x' % initial[0])
    except (OSError, TimeoutError) as exc:
        log('ERROR peer=%s:%s %s' % (addr[0],addr[1],exc))
    finally:
        for s in (upstream,c):
            if s:
                try: s.close()
                except OSError: pass


def main():
    runtime = load(RUNTIME_FILE,{})
    port = int(runtime.get('listeners',{}).get('gateway',os.getenv('PORT','8080')))
    print('[gateway-router] MODE=direct-http-or-tls', flush=True)
    print('[gateway-router] TLS -> xhttp-reality:%s HTTP /xhttp -> xhttp-tls:%s' % (runtime['listeners']['xhttp_reality'],runtime['listeners']['xhttp_tls']), flush=True)
    with socket.socket(socket.AF_INET,socket.SOCK_STREAM) as s:
        s.setsockopt(socket.SOL_SOCKET,socket.SO_REUSEADDR,1); tune(s); s.bind(('0.0.0.0',port)); s.listen(1024)
        print('[gateway-router] LISTEN 0.0.0.0:%d' % port, flush=True)
        while True:
            c, addr = s.accept(); tune(c); threading.Thread(target=handle,args=(c,addr),daemon=True).start()

if __name__ == '__main__': main()
