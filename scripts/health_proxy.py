import os,socket,threading,select
from pathlib import Path
from urllib.parse import urlsplit
PORT=int(os.getenv('PORT','8080')); REALITY=('127.0.0.1',int(os.getenv('XRAY_PORT','10087'))); XHTTP=('127.0.0.1',int(os.getenv('XRAY_HTTP_PORT','10086'))); SITE=Path('/opt/xray/site'); SUB=Path(os.getenv('SUBSCRIPTION_FILE','/data/subscription.txt')); TOKEN=Path(os.getenv('SUBSCRIPTION_TOKEN_FILE','/data/subscription_token.txt')); PATH=os.getenv('XHTTP_PATH','/xhttp')
def resp(code,typ,body):
    b=body.encode() if isinstance(body,str) else body
    return f'HTTP/1.1 {code}\r\nContent-Type: {typ}\r\nContent-Length: {len(b)}\r\nConnection: close\r\nCache-Control: no-store\r\n\r\n'.encode()+b
def relay(a,b,initial=b''):
    if initial:b.sendall(initial)
    while True:
        r,_,_=select.select((a,b),(),(a,b),300)
        if not r:return
        for s in r:
            d=b if s is a else a; x=s.recv(65536)
            if not x:return
            d.sendall(x)
def handle(c):
    try:
        c.settimeout(10); d=c.recv(16384)
        if not d:return
        if d.startswith(b'GET ') or d.startswith(b'HEAD '):
            first=d.split(b'\r\n',1)[0].decode('ascii','ignore').split(' '); path=urlsplit(first[1]).path
            if path=='/health':c.sendall(resp(200,'text/plain','OK\n'));return
            if path.startswith('/sub/') and path=='/sub/'+TOKEN.read_text().strip():c.sendall(resp(200,'text/plain',SUB.read_bytes()));return
            if path==PATH or path.startswith(PATH+'/'): up=socket.create_connection(XHTTP,10); relay(c,up,d); up.close(); return
            if path=='/': c.sendall(resp(200,'text/plain','Railway Multi-SNI REALITY\n'));return
            c.sendall(resp(404,'text/plain','Not Found\n'));return
        up=socket.create_connection(REALITY,10); relay(c,up,d); up.close()
    except Exception: pass
    finally:c.close()
with socket.socket() as s:
    s.setsockopt(socket.SOL_SOCKET,socket.SO_REUSEADDR,1);s.bind(('0.0.0.0',PORT));s.listen(256)
    while True:
        c,_=s.accept();threading.Thread(target=handle,args=(c,),daemon=True).start()
