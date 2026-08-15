# Portable Railway deployment helpers

This directory documents the Railway control-plane prerequisites for the portable deployment. The supported first-deployment flow is intentionally browser-based; no local computer, Railway CLI, or Railway API token is required.

## Supported first-deployment flow

```text
README
  ↓
Deploy on Railway
  ↓
Select repository
  ↓
Deploy Repo
  ↓
First deployment may fail
  ↓
Settings → Networking → Generate Domain
  target/application port = 8080
  ↓
Settings → Networking → TCP Proxy
  target/application port = 8080
  ↓
Railway generates:
  <current>.up.railway.app
  <current>.proxy.rlwy.net:<RANDOM>
  ↓
Click Deploy / Redeploy again
  ↓
Normal startup
```

The first failure is expected when the service has not yet received Railway networking resources. `scripts/start.sh` fails fast with an explicit message instead of inventing a hostname/port or reusing an old deployment value.

## Fixed target vs dynamic values

Fixed:

```text
Gateway / Public Domain target = 8080
TCP Proxy application target   = 8080
```

Dynamic per Railway deployment:

```text
RAILWAY_PUBLIC_DOMAIN
RAILWAY_TCP_PROXY_DOMAIN
RAILWAY_TCP_PROXY_PORT
```

`RAILWAY_TCP_PROXY_PORT` is assigned by Railway and must never be hard-coded. A value such as `42827` belongs only to one historical deployment.

## Runtime values

After the manual networking steps and the next Deploy/Redeploy, the container consumes:

```text
RAILWAY_PUBLIC_DOMAIN
RAILWAY_TCP_PROXY_DOMAIN
RAILWAY_TCP_PROXY_PORT
RAILWAY_TCP_APPLICATION_PORT=8080
```

Only then does `scripts/start.sh` generate the runtime identity/configuration and subscription endpoints.

## Subscription contract

```text
PRIMARY
https://<current Railway public domain>/sub/<current token>

FALLBACK
http://<current Railway TCP proxy domain>:<current Railway TCP proxy port>/sub/<current token>
```

The placeholders above are documentation notation only. The running instance replaces them with the current Railway-generated values.

The seven REALITY/XHTTP nodes use the current TCP Proxy domain and current Railway-assigned external port.

## Verification

After the second deployment becomes healthy, verify:

```text
1. Public Domain exists and targets 8080
2. TCP Proxy exists and targets 8080
3. TCP Proxy external port is Railway-generated
4. /health returns 200
5. /ready returns 200
6. Subscription returns 8 nodes
7. Primary uses the current *.up.railway.app domain
8. Fallback uses the current *.proxy.rlwy.net:<random-port>
9. HTTPS/XHTTP client node works
10. REALITY/XHTTP client nodes work
```

Use `deploy/verify.sh` only as an optional post-deployment diagnostic. It is not required to start the application.

## Security

The application does not require a Railway API token.

Never commit:

- `RAILWAY_API_TOKEN`
- Railway project/service/environment tokens
- UUIDs or REALITY private keys
- subscription tokens
- `/data` runtime files
