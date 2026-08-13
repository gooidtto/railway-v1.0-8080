import os
import socket
from pathlib import Path

def candidate_list(path=None):
    p=Path(path or os.getenv('REALITY_SNI_CANDIDATES_FILE','config/reality-sni-candidates.txt'))
    if not p.exists(): return ['www.cloudflare.com','www.microsoft.com','www.bing.com','www.apple.com']
    return list(dict.fromkeys(v.strip() for v in p.read_text().splitlines() if v.strip() and not v.lstrip().startswith('#')))

def validated_candidates(values):
    if os.getenv('REALITY_SNI_VALIDATE_DNS','0').lower() not in {'1','true','yes','on'}: return values
    out=[]
    for host in values:
        try: socket.getaddrinfo(host,443,type=socket.SOCK_STREAM); out.append(host)
        except OSError: pass
    return out
