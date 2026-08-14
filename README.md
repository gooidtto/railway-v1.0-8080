# railway-v1.0-8080-portable

Portable Railway + Xray XHTTP/REALITY deployment derived from the verified `railway-v1.0-8080` baseline.

This branch is specifically intended for:

**Download ZIP → create a new Railway project/service → configure Public Networking + TCP Proxy + Volume → deploy.**

## Why this branch exists

The original project contained deployment-specific public-domain defaults. A copied project can therefore retain an old hostname if the runtime does not replace it correctly.

This portable branch removes that dependency from the image and makes Railway's runtime-provided values authoritative:

- `RAILWAY_PUBLIC_DOMAIN` → current public HTTPS hostname
- `RAILWAY_TCP_PROXY_DOMAIN` → current TCP Proxy hostname
- `RAILWAY_TCP_PROXY_PORT` → current TCP Proxy external port
- `PORT` → current Railway HTTP target port
- `RAILWAY_VOLUME_MOUNT_PATH` → current persistent volume mount path

Railway documents these variables as system-provided deployment variables. citeturn1search0turn1search7

## Architecture

```text
                    Railway Public Networking
                              │
                     HTTPS / current domain
                              │
                              ▼
                        Gateway :$PORT
                     (default target :8080)
                              │
             ┌────────────────┼─────────────────┐
             │                │                 │
           /sub/*           /health           /ready
             │
             └────────────── site/ + subscription

HTTP/XHTTP path /xhttp ───────────────► 127.0.0.1:10086

Railway TCP Proxy ────────────────────► 127.0.0.1:10087
                                          │
                                      REALITY+XHTTP
                                          │
                                  7 verified SNI nodes
```

The subscription contains **8 nodes**:

1. One HTTPS + TLS + XHTTP node using the current Railway public domain.
2. Seven XHTTP + REALITY nodes using the current Railway TCP Proxy endpoint and the verified SNI pool.

## Portable deployment checklist

### 1. Create a new Railway project/service

Deploy this branch/repository as a new service. Railway will build the included Dockerfile. Railway supports Dockerfile-based deployments and uses the service's configured start/deploy settings. citeturn0search5turn0search10

### 2. Public Networking

Generate a Railway public domain under **Settings → Networking → Public Networking**.

The application must listen on Railway's injected `PORT`; this branch binds the gateway to that port and defaults to `8080` when running outside Railway. Railway explicitly requires the public application to listen on the provided `PORT`. citeturn1search7turn1search4

### 3. TCP Proxy

Create the Railway TCP Proxy for the service.

The runtime automatically reads:

```text
RAILWAY_TCP_PROXY_DOMAIN
RAILWAY_TCP_PROXY_PORT
```

No old TCP hostname or port should be copied into the repository.

The generated REALITY subscription nodes therefore follow the **new Railway service's actual TCP Proxy configuration**.

### 4. Persistent Volume

Attach a Railway Volume at:

```text
/data
```

The runtime persists:

```text
/data/uuid.txt
/data/reality_private_key.txt
/data/reality_public_key.txt
/data/vless_decryption.txt
/data/vless_encryption.txt
/data/subscription_token.txt
/data/subscription_url.txt
/data/subscription.txt
```

Railway volumes are runtime storage and persist across deploys/restarts. citeturn1search10

### 5. Healthcheck

`railway.toml` configures:

```text
healthcheckPath = /health
healthcheckTimeout = 30
```

The gateway returns `200 OK` from `/health` once the HTTP gateway is available. Railway uses healthchecks to decide whether a new deployment is ready to receive traffic. citeturn0search0turn0search2

`/ready` is additionally available for diagnostics and only becomes `200` after Xray has passed its startup sequence.

## Startup behavior

`start.sh` deliberately fails fast if a portable deployment does not have:

```text
RAILWAY_PUBLIC_DOMAIN
RAILWAY_TCP_PROXY_DOMAIN
RAILWAY_TCP_PROXY_PORT
```

The TCP Proxy values can also be supplied through the compatibility aliases already supported by the baseline:

```text
SERVER_HOST / SERVER_PORT
XRAY_TCP_PROXY_HOST / XRAY_TCP_PROXY_PORT
```

This is intentional. It is safer to fail with a clear startup error than to generate a subscription containing the previous Railway service's hostname or port.

At startup the log prints only non-secret routing information:

```text
[startup] Railway public domain: ...
[startup] TCP proxy: ...
[startup] Gateway: 0.0.0.0:...
[startup] Xray REALITY: 127.0.0.1:10087
[startup] Xray HTTPS/XHTTP: 127.0.0.1:10086
```

Private keys, UUIDs and subscription tokens are never printed.

## Verified SNI pool

The production pool remains exactly seven verified values:

- `www.cloudflare.com`
- `www.bing.com`
- `www.canva.com`
- `www.notion.so`
- `store.epicgames.com`
- `www.gog.com`
- `www.gamespot.com`

Do not add unverified SNI values to the portable baseline.

## Repository layout

```text
.
├── config/
│   └── reality-sni-candidates.txt
├── scripts/
│   ├── generate.py
│   ├── health_proxy.py
│   └── start.sh
├── site/
│   └── index.html
├── Dockerfile
├── railway.toml
└── README.md
```

## Configuration ownership

`start.sh` owns runtime discovery and persistent material.

`generate.py` owns Xray configuration and subscription generation.

`health_proxy.py` owns the HTTP gateway and TCP forwarding.

`railway.toml` owns deployment healthcheck/restart configuration.

`Dockerfile` contains no deployment-specific Railway hostname.

## Subscription

After a successful startup, the current subscription URL is written to:

```text
/data/subscription_url.txt
```

Its structure is:

```text
https://<CURRENT-RAILWAY-PUBLIC-DOMAIN>/sub/<CURRENT-TOKEN>
```

The token is generated once and persisted in the Railway Volume. The public domain is regenerated from Railway's current runtime environment on every startup, so a new Railway service does not inherit the old service's hostname.

## First deployment validation

After deployment, verify in this order:

```text
1. Build succeeds
2. Container starts
3. /health returns 200
4. /ready returns 200
5. startup log shows the NEW public domain
6. startup log shows the NEW TCP Proxy host:port
7. /data/subscription_url.txt contains the NEW public domain
8. HTTPS subscription returns 8 nodes
9. Client tests the HTTPS/XHTTP node
10. Client tests the REALITY/XHTTP nodes
```

Do not treat a successful Docker build as proof of a successful runtime. Railway separates build/deploy stages, and healthchecks are evaluated after the container starts. citeturn0search5turn0search0

## Security / repository hygiene

Never commit:

- UUIDs
- REALITY private keys
- REALITY public keys generated for a deployment
- VLESS encryption/decryption material
- subscription tokens
- `/data` runtime artifacts

The repository contains only generation logic and the verified SNI pool.

## Stability rule

This branch is a **portable deployment variant**, not a replacement for the current production baseline.

Keep changes isolated here until a fresh Railway deployment has passed:

- website test
- `/health`
- `/ready`
- HTTPS/XHTTP client test
- TCP Proxy/REALITY client test
- subscription node-count and hostname validation

Only after those tests pass should the changes be considered for promotion to `main`.
