import base64, json, os
from pathlib import Path
from urllib.parse import quote
from select_reality_sni import candidate_list, validated_candidates

def env(name, default=None, required=False):
    value=os.getenv(name,default)
    if required and not value: raise SystemExit(f'ERROR: missing {name}')
    return value

data=Path(env('DATA_DIR','/data')); config_path=Path(env('CONFIG','/etc/xray/config.json'))
xray_port=int(env('XRAY_PORT','10087')); xray_http=int(env('XRAY_HTTP_PORT','10086'))
listen=env('XRAY_LISTEN','127.0.0.1'); host=env('SERVER_HOST',''); port=env('SERVER_PORT','')
uuid=env('UUID',required=True); private=env('PRIVATE_KEY',required=True); public=env('PUBLIC_KEY',required=True)
decryption=env('VLESS_DECRYPTION',required=True); encryption=env('VLESS_ENCRYPTION',required=True)
target=env('REALITY_TARGET','www.cloudflare.com:443')
fingerprint=env('REALITY_FINGERPRINT','chrome'); path=env('XHTTP_PATH','/xhttp'); mode=env('XHTTP_MODE','auto'); sid=env('SHORT_ID','50175c035ee132')
raw=validated_candidates(candidate_list()); limit=int(env('REALITY_SNI_LIMIT','19')); pool=raw[:limit]
if not pool: raise SystemExit('ERROR: no REALITY SNI candidates available')
reality={'listen':listen,'port':xray_port,'protocol':'vless','settings':{'clients':[{'id':uuid}],'decryption':decryption},'streamSettings':{'network':'xhttp','security':'reality','realitySettings':{'show':False,'target':target,'xver':0,'serverNames':pool,'privateKey':private,'shortIds':[sid]},'xhttpSettings':{'path':path,'mode':mode}}}
https={'listen':'127.0.0.1','port':xray_http,'protocol':'vless','settings':{'clients':[{'id':uuid}],'decryption':decryption},'streamSettings':{'network':'xhttp','security':'none','xhttpSettings':{'path':path,'mode':mode}}}
config={'log':{'loglevel':env('XRAY_LOGLEVEL','info')},'inbounds':[reality,https],'outbounds':[{'protocol':'freedom','tag':'direct'}]}
config_path.parent.mkdir(parents=True,exist_ok=True); tmp=str(config_path)+'.tmp'
with open(tmp,'w') as f: json.dump(config,f,indent=2); f.write('\n')
os.chmod(tmp,0o600); os.replace(tmp,config_path); data.mkdir(parents=True,exist_ok=True)
if not (host and port): raise SystemExit('ERROR: SERVER_HOST and SERVER_PORT are required for REALITY subscription nodes')
nodes=[]
for sni in pool:
    nodes.append(f"vless://{uuid}@{host}:{port}/?encryption={quote(encryption,safe='')}&security=reality&type=xhttp&fp={quote(fingerprint,safe='')}&sni={quote(sni,safe='')}&pbk={quote(public,safe='')}&sid={quote(sid,safe='')}&path={quote(path,safe='')}&mode={quote(mode,safe='')}#railway-xhttp-reality-{sni}")
text='\n'.join(nodes)+'\n'; (data/'vless.txt').write_text(text)
(data/'subscription.txt').write_text(base64.b64encode(text.encode()).decode()+'\n'); os.chmod(data/'subscription.txt',0o600)
(data/'reality-sni-list.txt').write_text('\n'.join(pool)+'\n')
print(f'REALITY SNI nodes generated: {len(nodes)}')
for sni in pool: print(f'REALITY SNI: {sni}')
