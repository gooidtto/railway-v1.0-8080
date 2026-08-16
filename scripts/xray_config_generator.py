#!/usr/bin/env python3
import json
import os
import re
import secrets
import subprocess
from pathlib import Path

DATA_DIR = Path(os.getenv("DATA_DIR", "/data"))
CONFIG = Path(os.getenv("XRAY_CONFIG", "/etc/xray/config.json"))
RUNTIME_FILE = DATA_DIR / "runtime.json"

def load_json(path):
    try: return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError): return {}

def persistent(name, producer):
    path = DATA_DIR / name
    if path.is_file():
        value = path.read_text(encoding="utf-8").strip()
        if value: return value
    value = producer().strip()
    if not value: raise SystemExit("ERROR: failed to generate %s" % name)
    path.write_text(value + "\n", encoding="utf-8"); os.chmod(path, 0o600); return value

def xray(args): return subprocess.check_output(["xray", *args], text=True, stderr=subprocess.STDOUT)
def make_uuid(): return xray(["uuid"])

def make_reality():
    out=xray(["x25519"]); private=public=""
    for line in out.splitlines():
        if ":" not in line: continue
        key,value=[x.strip() for x in line.split(":",1)]; key=key.lower().replace(" ","")
        if key=="privatekey" and not private: private=value
        elif (key.startswith("password") or key=="publickey") and not public: public=value
    if not private or not public: raise SystemExit("ERROR: unable to parse xray x25519 output")
    return private,public

def make_vless_keys():
    out=xray(["vlessenc"]); dec=enc=""; active=False
    for line in out.splitlines():
        if "ML-KEM-768" in line and "Post-Quantum" in line: active=True; continue
        if not active: continue
        if '"decryption"' in line and not dec: dec=line.split('"decryption"',1)[1].split(":",1)[1].strip().strip(",").strip('"')
        elif '"encryption"' in line and not enc: enc=line.split('"encryption"',1)[1].split(":",1)[1].strip().strip(",").strip('"')
        if dec and enc: break
    if not dec or not enc: raise SystemExit("ERROR: unable to parse xray vlessenc output")
    return dec,enc

def candidate_list():
    path=Path(os.getenv("REALITY_SNI_CANDIDATES_FILE","/opt/xray/config/reality-sni-candidates.txt"))
    if not path.is_file(): raise SystemExit("ERROR: REALITY SNI candidate file is missing")
    values=list(dict.fromkeys(x.strip().lower() for x in path.read_text(encoding="utf-8").splitlines() if x.strip() and not x.lstrip().startswith("#")))
    if not values: raise SystemExit("ERROR: REALITY SNI candidate pool is empty")
    return values

def normalize_target(value):
    value=(value or "").strip()
    if value.startswith(("http://","https://")): value=value.split("://",1)[1]
    value=value.strip("/").split("/",1)[0]
    if ":" not in value: value += ":443"
    host,port=value.rsplit(":",1)
    if not re.fullmatch(r"[A-Za-z0-9.-]+",host) or not port.isdigit(): raise SystemExit("ERROR: invalid REALITY_TARGET")
    return "%s:%d"%(host,int(port))

def main():
    runtime=load_json(RUNTIME_FILE)
    if not runtime: raise SystemExit("ERROR: runtime.json is missing")
    listeners=runtime.get("listeners",{}); reality_port=int(listeners["xhttp_reality"]); tls_port=int(listeners["xhttp_tls"]); DATA_DIR.mkdir(parents=True,exist_ok=True)
    uuid=persistent("uuid.txt",make_uuid)
    priv=DATA_DIR/"reality_private_key.txt"; pub=DATA_DIR/"reality_public_key.txt"
    if priv.is_file() and pub.is_file(): private_key=priv.read_text().strip(); public_key=pub.read_text().strip()
    else:
        private_key,public_key=make_reality(); priv.write_text(private_key+"\n"); pub.write_text(public_key+"\n"); os.chmod(priv,0o600); os.chmod(pub,0o600)
    enable=os.getenv("ENABLE_VLESS_ENCRYPTION","true").strip().lower() in {"1","true","yes","on"}
    dec_file=DATA_DIR/"vless_decryption.txt"; enc_file=DATA_DIR/"vless_encryption.txt"
    if enable:
        if dec_file.is_file() and enc_file.is_file() and dec_file.read_text().strip() and enc_file.read_text().strip(): decryption=dec_file.read_text().strip(); encryption=enc_file.read_text().strip()
        else:
            decryption,encryption=make_vless_keys(); dec_file.write_text(decryption+"\n"); enc_file.write_text(encryption+"\n"); os.chmod(dec_file,0o600); os.chmod(enc_file,0o600)
    else: decryption,encryption="none",""; dec_file.write_text("none\n"); enc_file.write_text("\n")
    sid=persistent("short_id.txt",lambda: os.getenv("SHORT_ID","").strip().lower() or secrets.token_hex(8))
    if not re.fullmatch(r"[0-9a-f]{2,16}",sid) or len(sid)%2: raise SystemExit("ERROR: invalid SHORT_ID")
    fingerprint=os.getenv("REALITY_FINGERPRINT","chrome").strip() or "chrome"; path=os.getenv("XHTTP_PATH","/xhttp").strip() or "/xhttp"; mode=os.getenv("XHTTP_MODE","auto").strip() or "auto"
    candidates=candidate_list(); target=normalize_target(os.getenv("REALITY_TARGET",candidates[0]+":443"))
    reality={"show":False,"target":target,"xver":0,"serverNames":candidates,"privateKey":private_key,"shortIds":[sid]}
    inbounds=[
        {"listen":"127.0.0.1","port":reality_port,"protocol":"vless","settings":{"clients":[{"id":uuid}],"decryption":decryption},"streamSettings":{"network":"xhttp","security":"reality","realitySettings":reality,"xhttpSettings":{"path":path,"mode":mode}}},
        {"listen":"127.0.0.1","port":tls_port,"protocol":"vless","settings":{"clients":[{"id":uuid}],"decryption":decryption},"streamSettings":{"network":"xhttp","security":"none","xhttpSettings":{"path":path,"mode":mode}}},
    ]
    config={"log":{"loglevel":os.getenv("XRAY_LOGLEVEL","info")},"inbounds":inbounds,"outbounds":[{"protocol":"freedom","tag":"direct"}]}
    CONFIG.parent.mkdir(parents=True,exist_ok=True); tmp=CONFIG.with_suffix(".json.tmp"); tmp.write_text(json.dumps(config,indent=2)+"\n"); os.chmod(tmp,0o600); os.replace(tmp,CONFIG)
    manifest={"schema":3,"uuid":uuid,"public_key":public_key,"short_id":sid,"encryption":encryption,"decryption":decryption,"vless_encryption_enabled":enable,"reality_sni":candidates,"reality_target":target,"fingerprint":fingerprint,"xhttp_path":path,"xhttp_mode":mode,"listeners":{"xhttp_reality":reality_port,"xhttp_tls":tls_port}}
    mf=DATA_DIR/"xray-manifest.json"; mf.write_text(json.dumps(manifest,indent=2)+"\n"); os.chmod(mf,0o600)
    print("[xray-config-generator] stable baseline: XHTTP + REALITY only",flush=True); print("[xray-config-generator] REALITY SNI count=%d"%len(candidates),flush=True); print("[xray-config-generator] listeners: reality=127.0.0.1:%d xhttp=127.0.0.1:%d"%(reality_port,tls_port),flush=True); print("[xray-config-generator] vless-encryption=%s"%( "enabled" if enable else "disabled"),flush=True)
if __name__=="__main__": main()
