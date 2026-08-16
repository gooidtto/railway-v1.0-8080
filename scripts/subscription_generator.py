import base64, json, os, secrets
from pathlib import Path
from urllib.parse import quote
DATA_DIR=Path(os.getenv("DATA_DIR","/data"))
def load(name):return json.loads((DATA_DIR/name).read_text(encoding="utf-8"))
def write(name,text,mode=0o600):
    path=DATA_DIR/name;tmp=path.with_suffix(path.suffix+".tmp");tmp.write_text(text,encoding="utf-8");os.chmod(tmp,mode);os.replace(tmp,path)
def q(v):return quote(str(v),safe="")
def vless(uuid,host,port,params,label):
    query="&".join("%s=%s"%(k,q(v)) for k,v in params.items() if v is not None and v!="")
    return "vless://%s@%s:%s?%s#%s"%(uuid,host,port,query,q(label))
def main():
    runtime=load("runtime.json");manifest=load("xray-manifest.json");r=runtime["railway"];uuid,sid,pbk=manifest["uuid"],manifest["short_id"],manifest["public_key"];common={"encryption":manifest["encryption"]} if manifest.get("encryption") else {};nodes=[]
    if r.get("public_domain"):
        nodes.append(vless(uuid,r["public_domain"],443,{**common,"security":"none","type":"xhttp","fp":manifest["fingerprint"],"sni":r["public_domain"],"alpn":"h2,http/1.1","path":manifest["xhttp_path"],"mode":manifest["xhttp_mode"]},"railway-xhttp-https-edge"))
    if r.get("tcp_proxy_domain") and r.get("tcp_proxy_port"):
        for sni in manifest["reality_sni"]:
            nodes.append(vless(uuid,r["tcp_proxy_domain"],r["tcp_proxy_port"],{**common,"security":"reality","type":"xhttp","fp":manifest["fingerprint"],"sni":sni,"pbk":pbk,"sid":sid,"path":manifest["xhttp_path"],"mode":manifest["xhttp_mode"]},"railway-xhttp-reality-%s"%sni))
    if not nodes:raise SystemExit("[subscription-generator] ERROR: no nodes generated")
    text="\n".join(nodes)+"\n";encoded=base64.b64encode(text.encode()).decode()+"\n";write("vless.txt",text);write("subscription.txt",encoded)
    if base64.b64decode(encoded.strip(),validate=True).decode().splitlines()!=text.strip().splitlines():raise SystemExit("[subscription-generator] ERROR: Base64 round-trip mismatch")
    token_file=DATA_DIR/"subscription_token.txt"
    if token_file.is_file() and token_file.read_text().strip():token=token_file.read_text().strip()
    else:token=secrets.token_urlsafe(32);write("subscription_token.txt",token+"\n")
    if r.get("public_domain"):
        url="https://%s/sub/%s"%(r["public_domain"],token);write("subscription_url.txt",url+"\n");write("subscription_endpoints.txt","PRIMARY=%s\n"%url)
    else:write("subscription_url.txt","");write("subscription_endpoints.txt","")
    if r.get("tcp_proxy_domain") and r.get("tcp_proxy_port"):write("tcp_proxy_endpoint.txt","TCP=%s:%s\n"%(r["tcp_proxy_domain"],r["tcp_proxy_port"]))
    else:write("tcp_proxy_endpoint.txt","")
    expected=1+len(manifest["reality_sni"]) if r.get("public_domain") and r.get("tcp_proxy_domain") and r.get("tcp_proxy_port") else 1
    if len(nodes)!=expected:raise SystemExit("[subscription-generator] ERROR: expected %d nodes, generated %d"%(expected,len(nodes)))
    print("[subscription-generator] stable baseline nodes=%d (1 HTTPS-edge + %d REALITY XHTTP)"%(len(nodes),len(manifest["reality_sni"])),flush=True);print("[subscription-generator] vless-encryption=%s"%( "enabled" if manifest.get("encryption") else "disabled"),flush=True);print("[subscription-generator] base64-roundtrip=OK",flush=True)
    if r.get("public_domain"):print("[subscription-generator] PRIMARY=https://%s/sub/%s"%(r["public_domain"],token),flush=True)
    if r.get("tcp_proxy_domain"):print("[subscription-generator] TCP=%s:%s"%(r["tcp_proxy_domain"],r["tcp_proxy_port"]),flush=True)
if __name__=="__main__":main()
