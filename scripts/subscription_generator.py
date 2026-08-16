import base64,json,os,secrets
from pathlib import Path
from urllib.parse import quote
DATA_DIR=Path(os.getenv('DATA_DIR','/data'))
def load(name): return json.loads((DATA_DIR/name).read_text())
def write(name,text,mode=0o600):
    p=DATA_DIR/name; t=p.with_suffix(p.suffix+'.tmp'); t.write_text(text); os.chmod(t,mode); os.replace(t,p)
def q(v): return quote(str(v),safe='')
def vless(uuid,host,port,params,label):
    query='&'.join('%s=%s'%(k,q(v)) for k,v in params.items() if v is not None and v!='')
    return 'vless://%s@%s:%s?%s#%s'%(uuid,host,port,query,q(label))
def main():
    runtime=load('runtime.json'); manifest=load('xray-manifest.json'); r=runtime['railway']; uuid=manifest['uuid']; sid=manifest['short_id']; pub=manifest['public_key']; common={'encryption':manifest['encryption']} if manifest.get('vless_encryption_enabled') and manifest.get('encryption') else {}; nodes=[]
    if r.get('public_domain'):
        nodes.append(vless(uuid,r['public_domain'],443,{**common,'security':'none','type':'xhttp','fp':manifest['fingerprint'],'sni':r['public_domain'],'alpn':'h2,http/1.1','path':manifest['xhttp_path'],'mode':manifest['xhttp_mode']},'railway-xhttp-https-edge'))
    if r.get('tcp_proxy_domain') and r.get('tcp_proxy_port'):
        for i,sni in enumerate(manifest.get('reality',{}).get('xhttp',[])[:3],1):
            nodes.append(vless(uuid,r['tcp_proxy_domain'],r['tcp_proxy_port'],{**common,'security':'reality','type':'xhttp','fp':manifest['fingerprint'],'sni':sni,'pbk':pub,'sid':sid,'path':manifest['xhttp_path'],'mode':manifest['xhttp_mode']},'railway-xhttp-reality-%d'%i))
    if len(nodes) != (4 if r.get('public_domain') and r.get('tcp_proxy_domain') and r.get('tcp_proxy_port') else 1): raise SystemExit('[subscription-generator] ERROR: expected 4 nodes, generated %d'%len(nodes))
    text='\n'.join(nodes)+'\n'; encoded=base64.b64encode(text.encode()).decode()+'\n'; write('vless.txt',text); write('subscription.txt',encoded)
    decoded=base64.b64decode(encoded.strip(),validate=True).decode();
    if [x for x in decoded.splitlines() if x.strip()] != nodes: raise SystemExit('[subscription-generator] ERROR: Base64 round-trip mismatch')
    tf=DATA_DIR/'subscription_token.txt'; token=tf.read_text().strip() if tf.is_file() and tf.read_text().strip() else secrets.token_urlsafe(32)
    if not tf.is_file() or not tf.read_text().strip(): write('subscription_token.txt',token+'\n')
    url='https://%s/sub/%s'%(r['public_domain'],token) if r.get('public_domain') else ''
    write('subscription_url.txt',url+'\n'); write('subscription_endpoints.txt',('PRIMARY='+url+'\n') if url else '')
    if r.get('tcp_proxy_domain') and r.get('tcp_proxy_port'): write('tcp_proxy_endpoint.txt','TCP=%s:%s\n'%(r['tcp_proxy_domain'],r['tcp_proxy_port']))
    print('[subscription-generator] stable baseline nodes=%d (1 HTTPS-edge + 3 shared XHTTP REALITY)'%len(nodes),flush=True)
    print('[subscription-generator] vless-encryption=%s'%('enabled' if common else 'disabled'),flush=True)
    print('[subscription-generator] base64-roundtrip=OK',flush=True)
    if url: print('[subscription-generator] PRIMARY='+url,flush=True)
    if r.get('tcp_proxy_domain') and r.get('tcp_proxy_port'): print('[subscription-generator] TCP=%s:%s'%(r['tcp_proxy_domain'],r['tcp_proxy_port']),flush=True)
if __name__=='__main__': main()
