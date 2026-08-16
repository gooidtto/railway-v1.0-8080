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
READY_FILE = DATA_DIR / '.xray-ready'


def load(path, default=None):
    try:
        return json.loads(path.read_text(encoding='utf-8'))
    except (OSError, ValueError):
        return default


def tune(s):
    for level, opt, val in ((socket.IPPROTO_TCP, socket.TCP_NODELAY, 1), (socket.SOL_SOCKET, socket.SO_KEEPALIVE, 1)):
        try:
            s.setsockopt(level, opt, val)
        except OSError:
            pass


def http_response(status, ctype, body, head=False):
    if isinstance(body, str):
        body = body.encode()
    reason = {200: 'OK', 404: 'Not Found', 405: 'Method Not Allowed', 503: 'Service Unavailable'}.get(status, 'OK')
    h = (
        'HTTP/1.1 %s %s\r\n'
        'Content-Type: %s\r\n'
        'Content-Length: %d\r\n'
        'Connection: keep-alive\r\n'
        'Keep-Alive: timeout=15, max=100\r\n'
        'Cache-Control: no-store\r\n'
        'X-Content-Type-Options: nosniff\r\n\r\n'
    ) % (status, reason, ctype, len(body))
    return h.encode() if head else h.encode() + body


def parse_http(data):
    try:
        head = data.split(b'\r\n\r\n', 1)[0]
        first = head.split(b'\r\n', 1)[0].decode('ascii')
        parts = first.split(' ', 2)
        if len(parts) != 3 or not parts[2].startswith('HTTP/'):
            return None
        target = urlsplit(parts[1])
        return parts[0], target.path or '/', target.netloc
    except (UnicodeDecodeError, ValueError):
        return None


def tls_handshake_bytes(data):
    """Return complete TLS handshake bytes reconstructed across records.

    ClientHello is commonly fragmented across TCP reads and can also span
    multiple TLS records. The old router parsed only the first record, which
    produced malformed SNI values such as ``www.cloudflare.\\x16\\x03\\x01``.
    """
    if len(data) < 5 or data[0] != 0x16 or data[1] != 0x03:
        return None
    pos = 0
    handshake = bytearray()
    while pos + 5 <= len(data):
        if data[pos] != 0x16 or data[pos + 1] != 0x03:
            break
        record_len = int.from_bytes(data[pos + 3:pos + 5], 'big')
        end = pos + 5 + record_len
        if end > len(data):
            return None
        handshake.extend(data[pos + 5:end])
        if len(handshake) >= 4:
            hello_len = int.from_bytes(handshake[1:4], 'big')
            if handshake[0] == 0x01 and len(handshake) >= 4 + hello_len:
                return bytes(handshake[:4 + hello_len])
            if handshake[0] != 0x01:
                return None
        pos = end
    return None


def tls_sni(data):
    """Extract SNI from a complete ClientHello without terminating TLS."""
    try:
        hello = tls_handshake_bytes(data)
        if not hello or hello[0] != 0x01:
            return ''
        p = 4
        if p + 2 + 32 + 1 > len(hello):
            return ''
        p += 2 + 32
        sid_len = hello[p]
        p += 1 + sid_len
        if p + 2 > len(hello):
            return ''
        cs_len = int.from_bytes(hello[p:p + 2], 'big')
        p += 2 + cs_len
        if p + 1 > len(hello):
            return ''
        comp_len = hello[p]
        p += 1 + comp_len
        if p + 2 > len(hello):
            return ''
        ext_len = int.from_bytes(hello[p:p + 2], 'big')
        p += 2
        end = min(len(hello), p + ext_len)
        while p + 4 <= end:
            typ = int.from_bytes(hello[p:p + 2], 'big')
            ln = int.from_bytes(hello[p + 2:p + 4], 'big')
            p += 4
            if p + ln > end:
                return ''
            if typ == 0:
                block = hello[p:p + ln]
                if len(block) < 2:
                    return ''
                list_len = int.from_bytes(block[:2], 'big')
                q = 2
                limit = min(len(block), 2 + list_len)
                while q + 3 <= limit:
                    name_type = block[q]
                    name_len = int.from_bytes(block[q + 1:q + 3], 'big')
                    q += 3
                    if q + name_len > limit:
                        return ''
                    if name_type == 0:
                        return block[q:q + name_len].decode('idna')
                    q += name_len
            p += ln
    except (IndexError, ValueError, UnicodeError):
        return ''
    return ''


def recv_initial(s, timeout=10):
    """Buffer enough bytes for HTTP headers or a complete TLS ClientHello."""
    s.settimeout(timeout)
    data = bytearray()
    while len(data) < 65536:
        chunk = s.recv(min(4096, 65536 - len(data)))
        if not chunk:
            break
        data.extend(chunk)
        raw = bytes(data)
        if b'\r\n\r\n' in raw:
            return raw
        if len(raw) >= 5 and raw[0] == 0x16 and raw[1] == 0x03:
            if tls_handshake_bytes(raw) is not None:
                return raw
        if len(raw) >= 8 and not raw.startswith((b'GET ', b'POST ', b'HEAD ', b'PUT ', b'OPTIONS ', b'PATCH ', b'DELETE ', b'CONNECT ')) and raw[0] != 0x16:
            return raw
    return bytes(data)


def relay(a, b, initial=b''):
    tune(a)
    tune(b)
    a.settimeout(None)
    b.settimeout(None)
    if initial:
        b.sendall(initial)
    while True:
        readable, _, _ = select.select((a, b), (), (), 300)
        if not readable:
            return
        for src in readable:
            dst = b if src is a else a
            chunk = src.recv(65536)
            if not chunk:
                return
            dst.sendall(chunk)


def connect(port):
    s = socket.create_connection(('127.0.0.1', int(port)), timeout=10)
    tune(s)
    return s


def website(c, method, path):
    if path == '/health':
        c.sendall(http_response(200, 'text/plain; charset=utf-8', 'OK\n', method == 'HEAD'))
        return True
    if path == '/ready':
        ok = READY_FILE.exists()
        c.sendall(http_response(200 if ok else 503, 'text/plain; charset=utf-8', 'READY\n' if ok else 'NOT READY\n', method == 'HEAD'))
        return True
    if path.startswith('/sub/'):
        token = TOKEN_FILE.read_text().strip() if TOKEN_FILE.is_file() else ''
        if token and path == '/sub/' + token and SUB_FILE.is_file():
            c.sendall(http_response(200, 'text/plain; charset=utf-8', SUB_FILE.read_bytes(), method == 'HEAD'))
        else:
            c.sendall(http_response(404, 'text/plain; charset=utf-8', 'Not Found\n', method == 'HEAD'))
        return True
    if path == '/sub':
        c.sendall(http_response(404, 'text/plain; charset=utf-8', 'Not Found\n', method == 'HEAD'))
        return True
    if method not in {'GET', 'HEAD'}:
        c.sendall(http_response(405, 'text/plain; charset=utf-8', 'Method Not Allowed\n'))
        return True
    rel = 'index.html' if path == '/' else path.lstrip('/')
    target = (SITE_DIR / rel).resolve()
    if SITE_DIR not in target.parents and target != SITE_DIR or not target.is_file():
        c.sendall(http_response(404, 'text/plain; charset=utf-8', 'Not Found\n', method == 'HEAD'))
        return True
    body = target.read_bytes()
    types = {'.html': 'text/html; charset=utf-8', '.css': 'text/css; charset=utf-8', '.js': 'application/javascript; charset=utf-8', '.json': 'application/json', '.svg': 'image/svg+xml', '.png': 'image/png', '.jpg': 'image/jpeg', '.jpeg': 'image/jpeg'}
    c.sendall(http_response(200, types.get(target.suffix.lower(), 'application/octet-stream'), body, method == 'HEAD'))
    return True


def handle(c):
    upstream = None
    try:
        initial = recv_initial(c)
        if not initial:
            return
        runtime = load(RUNTIME_FILE, {})
        manifest = load(MANIFEST_FILE, {})
        ports = runtime.get('listeners', {})

        if initial[:1] == b'\x16' and len(initial) >= 3:
            sni = tls_sni(initial)
            reality = manifest.get('reality', {})
            if sni in set(reality.get('vision', [])):
                target = ports['vision_reality']
            elif sni in set(reality.get('grpc', [])):
                target = ports['grpc_reality']
            elif sni in set(reality.get('xhttp', [])):
                target = ports['xhttp_reality']
            else:
                print('[gateway-router] reject unknown TLS SNI=%s' % (sni or '-'), flush=True)
                return
            upstream = connect(target)
            relay(c, upstream, initial)
            return

        parsed = parse_http(initial)
        if parsed:
            method, path, _ = parsed
            xhttp_path = manifest.get('xhttp_path', '/xhttp')
            if path != xhttp_path and not path.startswith(xhttp_path + '/'):
                website(c, method, path)
                return
            upstream = connect(ports['xhttp_tls'])
            relay(c, upstream, initial)
            return

        # Opaque TCP remains the high-throughput Vision path. This is only used
        # when the connection is not HTTP and not a TLS ClientHello.
        upstream = connect(ports['vision_reality'])
        relay(c, upstream, initial)
    except (OSError, TimeoutError) as exc:
        print('[gateway-router] error=%s' % exc, flush=True)
    finally:
        for s in (upstream, c):
            if s:
                try:
                    s.close()
                except OSError:
                    pass


def main():
    runtime = load(RUNTIME_FILE, {})
    port = int(runtime.get('listeners', {}).get('gateway', os.getenv('PORT', '8080')))
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        s.bind(('0.0.0.0', port))
        s.listen(512)
        print('[gateway-router] listening=0.0.0.0:%d' % port, flush=True)
        while True:
            c, _ = s.accept()
            tune(c)
            threading.Thread(target=handle, args=(c,), daemon=True).start()


if __name__ == '__main__':
    main()
