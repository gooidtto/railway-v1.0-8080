import os
from urllib.parse import quote
from scripts.select_reality_sni import candidate_list, validated_candidates

def build_nodes(uuid,host,port,encryption,fingerprint,public_key,short_id,xhttp_path,xhttp_mode):
    limit=int(os.getenv('REALITY_SNI_LIMIT','12'))
    candidates=validated_candidates(candidate_list())[:limit]
    if not candidates: raise SystemExit('ERROR: no REALITY SNI candidates available')
    return [f"vless://{uuid}@{host}:{port}/?encryption={quote(encryption,safe='')}&security=reality&type=xhttp&fp={quote(fingerprint,safe='')}&sni={quote(s,safe='')}&pbk={quote(public_key,safe='')}&sid={quote(short_id,safe='')}&path={quote(xhttp_path,safe='')}&mode={quote(xhttp_mode,safe='')}#railway-xhttp-reality-{s}" for s in candidates], candidates
