#!/usr/bin/env bash
set -euo pipefail

# One-command Railway provisioning for the portable deployment.
#
# This runs OUTSIDE the container and uses the Railway control plane:
#   1. create a fresh project/service and deploy (optional --new)
#   2. generate the Railway HTTPS domain on port 8080
#   3. create a persistent volume at /data
#   4. create the Railway TCP Proxy targeting application port 8080
#   5. read back the Railway-generated domain/ports
#
# Nothing in this script hard-codes a Railway public hostname or TCP proxy
# external port. Railway generates those values for each new service.
#
# Prerequisites:
#   - Railway CLI installed
#   - authenticated Railway CLI (`railway login`) OR RAILWAY_API_TOKEN
#   - RAILWAY_API_TOKEN set for the TCP Proxy GraphQL mutation
#     (account/workspace token is the safest choice for a fresh project)
#   - curl and Python 3
#
# Usage:
#   ./deploy/provision.sh --new
#   ./deploy/provision.sh

CREATE_NEW=0
if [[ "${1:-}" == "--new" ]]; then CREATE_NEW=1; fi

command -v railway >/dev/null 2>&1 || { echo "[provision] ERROR: railway CLI is required" >&2; exit 1; }
command -v curl >/dev/null 2>&1 || { echo "[provision] ERROR: curl is required" >&2; exit 1; }
command -v python3 >/dev/null 2>&1 || { echo "[provision] ERROR: python3 is required" >&2; exit 1; }

if [[ "$CREATE_NEW" == "1" ]]; then
  echo "[provision] Creating a new Railway project/service and deploying..."
  railway up --new --yes
else
  echo "[provision] Deploying the currently linked Railway service..."
  railway up --yes
fi

echo "[provision] Generating Railway public domain → application port 8080"
railway domain --port 8080 --json >/tmp/railway-domain.json

# A persistent /data volume is required for UUID, REALITY keys and token material.
# If a volume already exists/attaches, keep it; otherwise create and attach one.
if ! railway volume list --json 2>/dev/null | python3 -c 'import json,sys; d=json.load(sys.stdin); print("ok") if d else sys.exit(1)' >/dev/null 2>&1; then
  echo "[provision] Creating persistent volume at /data"
  railway volume add --mount-path /data --yes --json >/tmp/railway-volume.json || {
    echo "[provision] ERROR: could not create /data volume" >&2
    exit 1
  }
else
  echo "[provision] Existing volume detected; leaving it unchanged"
fi

echo "[provision] Reading project/service/environment IDs"
railway status --json >/tmp/railway-status.json
python3 - <<'PY'
import json
p='/tmp/railway-status.json'
d=json.load(open(p,encoding='utf-8'))
# Railway CLI status is intentionally inspected defensively because the exact
# JSON envelope can evolve. Find the first project/environment/service IDs.
ids={}
def walk(x):
    if isinstance(x,dict):
        for k,v in x.items():
            if k in ('projectId','environmentId','serviceId') and isinstance(v,str) and v:
                ids[k]=v
            if k == 'id' and isinstance(v,str) and v:
                # Keep named IDs when their parent object is recognized below.
                pass
            walk(v)
    elif isinstance(x,list):
        for v in x: walk(v)
walk(d)
for k in ('projectId','environmentId','serviceId'):
    if not ids.get(k):
        raise SystemExit(f'[provision] ERROR: could not find {k} in railway status --json')
open('/tmp/railway-ids.env','w').write('\n'.join(f'{k.upper()}={v}' for k,v in ids.items())+'\n')
PY
# shellcheck disable=SC1091
. /tmp/railway-ids.env

: "${RAILWAY_API_TOKEN:?Set RAILWAY_API_TOKEN to create the TCP Proxy through Railway's Public API}"

# Railway's public GraphQL API exposes tcpProxyCreate. The external proxy
# domain and proxy port are assigned by Railway; only applicationPort=8080 is
# supplied by this project.
python3 - <<'PY'
import json, os, subprocess, sys, urllib.request

query='''mutation tcpProxyCreate($input: TCPProxyCreateInput!) { tcpProxyCreate(input: $input) { id applicationPort domain proxyPort serviceId environmentId } }'''
variables={"input":{
    "environmentId":os.environ["ENVIRONMENTID"],
    "serviceId":os.environ["SERVICEID"],
    "applicationPort":8080,
}}
payload=json.dumps({"query":query,"variables":variables}).encode()
req=urllib.request.Request(
    'https://backboard.railway.com/graphql/v2',
    data=payload,
    headers={'Authorization':'Bearer '+os.environ['RAILWAY_API_TOKEN'],'Content-Type':'application/json'},
    method='POST')
with urllib.request.urlopen(req,timeout=30) as r:
    data=json.load(r)
if data.get('errors'):
    # A proxy may already exist; surface the exact API error rather than
    # silently creating a second mapping.
    print(json.dumps(data,indent=2),file=sys.stderr)
    raise SystemExit(1)
proxy=data.get('data',{}).get('tcpProxyCreate')
if not proxy:
    raise SystemExit('[provision] ERROR: Railway API returned no TCP proxy')
print('[provision] TCP Proxy created:')
print('  applicationPort =',proxy['applicationPort'])
print('  domain          =',proxy['domain'])
print('  proxyPort       =',proxy['proxyPort'])
json.dump(proxy,open('/tmp/railway-tcp-proxy.json','w'),indent=2)
PY

echo "[provision] Provisioning complete. Railway-generated values:"
python3 - <<'PY'
import json
try:
    d=json.load(open('/tmp/railway-domain.json',encoding='utf-8'))
    print('  Public domain:', d.get('domain') or d.get('url') or d)
except Exception: pass
try:
    d=json.load(open('/tmp/railway-tcp-proxy.json',encoding='utf-8'))
    print('  TCP proxy:', d['domain']+':'+str(d['proxyPort']))
    print('  TCP target:', d['applicationPort'])
except Exception: pass
PY

echo
cat <<'EOF'
Next:
  - Railway runtime will expose RAILWAY_PUBLIC_DOMAIN.
  - Railway runtime will expose RAILWAY_TCP_PROXY_DOMAIN.
  - Railway runtime will expose RAILWAY_TCP_PROXY_PORT.
  - Railway runtime will expose RAILWAY_TCP_APPLICATION_PORT=8080.
  - The container generates PRIMARY and FALLBACK subscription URLs from
    those runtime values; no Railway hostname/port is persisted in the code.
  - Run deploy/verify.sh after the service reaches a healthy state.
EOF
