#!/usr/bin/env python3
import json, os, re, secrets, subprocess
from pathlib import Path
DATA_DIR=Path(os.getenv('DATA_DIR','/data')); CONFIG=Path(os.getenv('XRAY_CONFIG','/etc/xray/config.json')); RUNTIME_FILE=DATA_DIR/'runtime.json'
def read(path, default=None):
    try: return json.loads(path.read_text())
    except (OSError,ValueError): return default
def persistent(name, producer):
    p=DATA_DIR/name
    if p.is_file() and p.read_text().strip(): return p.read_text().strip()
    v=producer().strip()
    if not v: raise SystemExit('ERROR: failed to generate '+name)
    p.write_text(v+'\n'); os.chmod(p,0o600); return v
def xray(args): return subprocess.check_output(['xray',*args],text=True,stderr=subprocess.STDOUT)
def make_uuid(): return xray(['uuid']).strip()
def make_reality():
    values={}
    for line in xray(['x25519']).splitlines():
        if ':' in line:
            k,v=[x.strip() for x in line.split(':',1)]; values[k.lower().replace(' ','')]=v
    private=values.get('privatekey',''); public=values.get('publickey','') or values.get('password(publickey)','') or values.get('password','')
    if not private or not public: raise SystemExit('ERROR: unable to parse xray x25519 output')
    return private,public
def make_vless_keys():
    out=xray(['vlessenc']); dec=enc=''; active=False
    for line in out.splitlines():
        if 'ML-KEM-768' in line and 'Post-Quantum' in line: active=True; continue
        if active and '"decryption"' in line: dec=line.split('"decryption"',1)[1].split(':',1)[1].strip().strip(',').strip('"')
        elif active and '"encryption"' in line: enc=line.split('"encryption"',1)[1].split(':',1)[1].strip().strip(',').strip('"')
        if dec and enc: break
    return dec,enc
def candidates():
    raw=os.getenv('REALITY_SNI_CANDIDATES','').strip()
    if raw: vals=[x.strip().lower() for x in raw.split(',') if x.strip()]
    else:
        p=Path('/opt/xray/config/reality-sni-candidates.txt')
        vals=[x.strip().lower() for x in p.read_text().splitlines() if x.strip() and not x.lstrip().startswith('#')] if p.is_file() else ['www.cloudflare.com','www.bing.com','www.canva.com']
    return list(dict.fromkeys(vals))[:8]
def main():
    runtime=read(RUNTIME_FILE)
    if not runtime: raise SystemExit('ERROR: runtime.json missing')
    DATA_DIR.mkdir(parents=True,exist_ok=True)
    uuid=persistent('uuid.txt',make_uuid)
    privf=DATA_DIR/'reality_private_key.txt'; pubf=DATA_DIR/'reality_public_key.txt'
    if privf.is_file() and pubf.is_file(): private=privf.read_text().strip(); public=pubf.read_text().strip()
    else:
        private,public=make_reality(); privf.write_text(private+'\n'); pubf.write_text(public+'\n'); os.chmod(privf,0o600); os.chmod(pubf,0o600)
    enabled=os.getenv('ENABLE_VLESS_ENCRYPTION','').strip().lower() in {'1','true','yes','on'}
    if enabled:
        df=DATA_DIR/'vless_decryption.txt'; ef=DATA_DIR/'vless_encryption.txt'
        if df.is_file() and ef.is_file() and df.read_text().strip() and ef.read_text().strip(): dec=df.read_text().strip(); enc=ef.read_text().strip()
        else:
            dec,enc=make_vless_keys();
            if not dec or not enc: raise SystemExit('ERROR: VLESS encryption key generation failed')
            df.write_text(dec+'\n'); ef.write_text(enc+'\n'); os.chmod(df,0o600); os.chmod(ef,0o600)
    else:
        dec='none'; enc=''; (DATA_DIR/'vless_decryption.txt').write_text('none\n'); (DATA_DIR/'vless_encryption.txt').write_text('\n')
    sid=persistent('short_id.txt',lambda: os.getenv('SHORT_ID','').strip().lower() or secrets.token_hex(8))
    if not re.fullmatch(r'[0-9a-f]{2,16}',sid) or len(sid)%2: raise SystemExit('ERROR: invalid short_id')
    path=os.getenv('XHTTP_PATH','/xhttp').strip() or '/xhttp'; mode=os.getenv('XHTTP_MODE','auto').strip() or 'auto'; fp=os.getenv('REALITY_FINGERPRINT','chrome').strip() or 'chrome'
    snis=candidates(); target=snis[0]+':443'; ports=runtime['listeners']
    reality={'show':False,'target':target,'xver':0,'serverNames':snis,'privateKey':private,'shortIds':[sid]}
    xhttp={'path':path,'mode':mode,'extra':{'xPaddingBytes':'100-1000','scStreamUpServerSecs':'20-80','scMaxEachPostBytes':1000000}}
    def inbound(port,security,real=False):
        stream={'network':'xhttp','security':security,'xhttpSettings':xhttp}
        if real: stream['realitySettings']=reality
        return {'listen':'127.0.0.1','port':port,'protocol':'vless','settings':{'clients':[{'id':uuid}],'decryption':dec},'streamSettings':stream}
    config={'log':{'loglevel':os.getenv('XRAY_LOGLEVEL','info')},'inbounds':[inbound(ports['xhttp_reality'],'reality',True),inbound(ports['xhttp_tls'],'none')],'outbounds':[{'protocol':'freedom','tag':'direct'}]}
    CONFIG.parent.mkdir(parents=True,exist_ok=True); tmp=CONFIG.with_suffix('.tmp'); tmp.write_text(json.dumps(config,indent=2)+'\n'); os.chmod(tmp,0o600); os.replace(tmp,CONFIG)
    manifest={'schema':4,'uuid':uuid,'public_key':public,'short_id':sid,'encryption':enc,'decryption':dec,'vless_encryption_enabled':enabled,'reality':{'xhttp':snis},'reality_targets':{'xhttp':target},'ports':{'xhttp_reality':ports['xhttp_reality'],'xhttp_tls':ports['xhttp_tls']},'xhttp_path':path,'xhttp_mode':mode,'fingerprint':fp}
    (DATA_DIR/'xray-manifest.json').write_text(json.dumps(manifest,indent=2)+'\n'); os.chmod(DATA_DIR/'xray-manifest.json',0o600)
    print('[xray-config-generator] stable baseline: one XHTTP REALITY + one HTTPS-edge XHTTP',flush=True)
    print('[xray-config-generator] REALITY serverNames=%s target=%s'%(','.join(snis),target),flush=True)
    print('[xray-config-generator] vless-encryption=%s'%('enabled' if enabled else 'disabled'),flush=True)
    print('[xray-config-generator] listeners: reality=127.0.0.1:%s xhttp=127.0.0.1:%s'%(ports['xhttp_reality'],ports['xhttp_tls']),flush=True)
if __name__=='__main__': main()
