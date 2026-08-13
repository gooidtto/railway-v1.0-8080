# railway-v1.0-8080

Railway + Xray XHTTP/REALITY deployment with a verified 7-SNI pool.

## Current architecture

The repository follows the verified `railway-v8.9-8080` gateway pattern:

```text
Public HTTPS :443
        │
        ▼
Railway gateway :8080
        ├── /sub/*, /health, /ready, site → HTTP handler
        ├── /xhttp/* → Xray XHTTP :10086
        └── non-HTTP/TCP → Xray REALITY + XHTTP :10087
```

The subscription contains **8 nodes**:

1. `HTTPS + TLS + XHTTP` — `<public-domain>:443`
2. `Railway TCP Proxy + XHTTP + REALITY` — 7 verified SNI variants

## Verified SNI pool

These are the seven SNI values currently retained because they were confirmed working in client tests:

- `www.cloudflare.com`
- `www.bing.com`
- `www.canva.com`
- `www.notion.so`
- `store.epicgames.com`
- `www.gog.com`
- `www.gamespot.com`

Do not add unverified SNI values to the production pool. Additions should be tested first and then committed to `config/reality-sni-candidates.txt`.

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

`generate.py` is the single source of truth for Xray configuration and subscription generation. The gateway implementation lives in `health_proxy.py`; startup and persistent material handling live in `start.sh`.

## Deployment requirements

Railway should provide:

- application/public HTTP port: `8080`
- TCP Proxy host and port for the REALITY nodes
- persistent volume mounted at `/data` (recommended so UUID, REALITY keys, VLESS material, and subscription token survive redeploys)

The public HTTPS hostname is configured with `PUBLIC_DOMAIN` and defaults to `railway-v10-8080-production.up.railway.app`.

## Subscription

The service writes the generated subscription to `/data/subscription.txt` and creates a random token on first startup.

The resulting endpoint is:

```text
https://<public-domain>/sub/<subscription-token>
```

The gateway also serves `/health` and `/ready` for deployment diagnostics.

## Configuration

Important environment variables:

| Variable | Default | Purpose |
|---|---|---|
| `PORT` | `8080` | Railway gateway port |
| `XRAY_PORT` | `10087` | REALITY + XHTTP inbound |
| `XRAY_HTTP_PORT` | `10086` | Plain XHTTP inbound behind HTTPS gateway |
| `XHTTP_PATH` | `/xhttp` | XHTTP path |
| `XHTTP_MODE` | `auto` | XHTTP mode |
| `REALITY_TARGET` | `www.cloudflare.com:443` | REALITY target |
| `REALITY_SNI_LIMIT` | `7` | Required production SNI count |
| `PUBLIC_DOMAIN` | `railway-v10-8080-production.up.railway.app` | Public HTTPS hostname |

UUID, REALITY key material, VLESS encryption material, and the subscription token are generated/persisted under `/data` when absent.

## Security and repository hygiene

- No generated credentials, UUIDs, private keys, subscription tokens, or `/data` artifacts belong in Git.
- Runtime secrets are persisted only under the Railway volume.
- The repository intentionally contains only the verified SNI pool.
- Changes to gateway routing should be tested against both HTTPS/XHTTP and TCP Proxy/REALITY before deployment.

## Stability baseline

The current production baseline is the implementation that was verified with the 7-SNI pool plus the HTTPS/XHTTP node. Preserve this baseline when making future changes; test new transport or SNI changes separately before replacing it.
