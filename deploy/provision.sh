#!/usr/bin/env bash
set -euo pipefail

# One-command Railway provisioning for the portable deployment.
#
# The first deployment may fail its application startup because the fresh
# service has no generated public domain/TCP proxy yet. That is expected.
# This script then creates the control-plane resources and performs a final
# redeploy, after which start.sh can consume the Railway-generated variables.
#
# No public hostname or TCP proxy external port is hard-coded.
#
# Prerequisites:
#   - Railway CLI installed
#   - authenticated Railway CLI (`railway login`) OR RAILWAY_API_TOKEN
#   - RAILWAY_API_TOKEN for the TCP Proxy GraphQL mutation
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
: "${RAILWAY_API_TOKEN:?Set RAILWAY_API_TOKEN to create the TCP Proxy through Railway's Public API}"

if [[ "$CREATE_NEW" == "1" ]]; then
  echo "[provision] Creating a new Railway project/service and initial deployment..."
  # The initial container may exit because the new service has no networking
  # resources yet. Do not abort before provisioning those resources.
  set +e
  railway up --new --yes
  INITIAL_STATUS=$?
  set -e
  echo "[provision] Initial deployment exit code: $INITIAL_STATUS (network bootstrap continues)"
else
  echo "[provision] Deploying the currently linked Railway service..."
  set +e
  railway up --yes
  INITIAL_STATUS=$?
  set -e
  echo "[provision] Initial deployment exit code: $INITIAL_STATUS"
fi

echo "[provision] Generating Railway public domain → application port 8080"
railway domain --port 8080 --json >/tmp/railway-domain.json

# Persistent storage is required for UUID, REALITY keys, VLESS material and token.
VOLUME_JSON=$(railway volume list --json 2>/dev/null || printf '')
if python3 - "$VOLUME_JSON" <<'PY'
import json,sys
raw=sys.argv[1]
try:
    d=json.loads(raw)
except Exception:
    raise SystemExit(1)
# Treat any volume in the linked environment as existing; the operator can
# attach/rename it separately if it is not already mounted at /data.
raise SystemExit(0 if d else 1)
PY
then
  echo "[provision] Existing Railway volume detected"
else
  echo "[provision] Creating persistent volume at /data"
  railway volume add --mount-path /data --yes --json >/tmp/railway-volume.json
fi

echo "[provision] Reading project/service/environment IDs"
railway status --json >/tmp/railway-status.json
python3 - <<'PY'
import json
p='/tmp/railway-status.json'
d=json.load(open(p,encoding='utf-8'))
ids={}
def walk(x):
    if isinstance(x,dict):
        for k,v in x.items():
            if k in ('projectId','environmentId','serviceId') and isinstance(v,str) and v:
                ids[k]=v
            walk(v)
    elif isinstance(x,list):
        for v in x: walk(v)
walk(d)
for k in ('projectId','environmentId','serviceId'):
    if not ids.get(k):
        raise SystemExit(f'[provision] ERROR: could not find {k} in railway status --json')
with open('/tmp/railway-ids.env','w',encoding='utf-8') as f:
    for k,v in ids.items(): f.write(f'{k.upper()}={v}\n')
PY
# shellcheck disable=SC1091
. /tmp/railway-ids.env

# Railway's public GraphQL API exposes tcpProxyCreate. The external proxy
# domain and proxy port are assigned by Railway; only applicationPort=8080 is
# supplied by this project.
python3 - <<'PY'
import json, os, sys, urllib.request
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
    # If a TCP proxy already exists, do not blindly create another one.
    message=json.dumps(data)
    if 'already' not in message.lower() and 'duplicate' not in message.lower():
        print(message,file=sys.stderr)
        raise SystemExit(1)
    print('[provision] TCP Proxy appears to already exist; continuing')
    sys.exit(0)
proxy=data.get('data',{}).get('tcpProxyCreate')
if not proxy:
    raise SystemExit('[provision] ERROR: Railway API returned no TCP proxy')
print('[provision] TCP Proxy created:')
print('  applicationPort =',proxy['applicationPort'])
print('  domain          =',proxy['domain'])
print('  proxyPort       =',proxy['proxyPort'])
json.dump(proxy,open('/tmp/railway-tcp-proxy.json','w'),indent=2)
PY

echo "[provision] Networking exists; redeploying so the container receives the generated variables"
railway redeploy --yes

# Read back the generated endpoints after the final deployment.
railway variable list --json >/tmp/railway-variables.json 2>/dev/null || true

echo "[provision] Provisioning complete."
python3 - <<'PY'
import json, os
try:
    d=json.load(open('/tmp/railway-domain.json',encoding='utf-8'))
    print('  Public domain:', d.get('domain') or d.get('url') or d)
except Exception: pass
try:
    d=json.load(open('/tmp/railway-tcp-proxy.json',encoding='utf-8'))
    print('  TCP proxy:', d['domain']+':'+str(d['proxyPort']))
    print('  TCP target:', d['applicationPort'])
except Exception:
    pass
PY

echo
cat <<'EOF'
Runtime contract:
  RAILWAY_PUBLIC_DOMAIN          = Railway-generated HTTPS domain
  RAILWAY_TCP_PROXY_DOMAIN       = Railway-generated TCP hostname
  RAILWAY_TCP_PROXY_PORT         = Railway-generated random external port
  RAILWAY_TCP_APPLICATION_PORT   = 8080

The container generates:
  PRIMARY  = https://<current public domain>/sub/<token>
  FALLBACK = http://<current TCP proxy domain>:<current TCP proxy port>/sub/<token>

No Railway hostname or external port is stored in source code.
EOF
