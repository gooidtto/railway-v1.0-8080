# Portable Railway provisioning

This directory handles the Railway control-plane part of a fresh deployment. It is intentionally separate from the container runtime.

## Goal

A fresh Railway service should end up with:

- Railway-generated `*.up.railway.app` public domain targeting **8080**
- Railway-generated TCP Proxy targeting **application port 8080**
- Railway-generated TCP proxy hostname and random external port
- persistent `/data` volume
- runtime-generated primary and fallback subscription URLs

No public hostname or external TCP port is hard-coded.

## One-command flow

Prerequisites:

```text
Railway CLI
curl
Python 3
RAILWAY_API_TOKEN
```

The API token is used only by the local provisioning script to call Railway's public GraphQL API. Do not put it in the repository or in the Docker image.

From the repository root:

```bash
chmod +x deploy/provision.sh deploy/verify.sh
RAILWAY_API_TOKEN='YOUR_ACCOUNT_OR_WORKSPACE_TOKEN' ./deploy/provision.sh --new
```

The provisioning script:

1. creates a fresh Railway project/service and deploys it;
2. generates the Railway public domain on port `8080`;
3. creates/uses persistent storage at `/data`;
4. creates a TCP Proxy with `applicationPort=8080`;
5. prints the Railway-generated TCP proxy domain and random external port.

Railway's public API supports service-domain creation, and Railway's TCP Proxy assigns its own proxy domain and external port while the caller supplies only the application port. The runtime exposes those generated values through Railway variables.

## Runtime values

The container uses these Railway-provided values as authoritative:

```text
RAILWAY_PUBLIC_DOMAIN
RAILWAY_TCP_PROXY_DOMAIN
RAILWAY_TCP_PROXY_PORT
RAILWAY_TCP_APPLICATION_PORT
```

Expected target:

```text
RAILWAY_TCP_APPLICATION_PORT=8080
```

The external TCP proxy port is **not fixed** and must never be set to an example such as `42827`.

## Subscription endpoints

After startup the persistent volume contains:

```text
/data/subscription_primary_url.txt
/data/subscription_fallback_url.txt
/data/subscription_endpoints.txt
```

The runtime generates:

```text
PRIMARY=https://<current Railway public domain>/sub/<current token>
FALLBACK=http://<current Railway TCP proxy domain>:<current Railway TCP proxy port>/sub/<current token>
```

The seven REALITY/XHTTP nodes also use the current Railway TCP proxy domain and current Railway-assigned external port.

## Verification

After the deployment is healthy:

```bash
./deploy/verify.sh
```

The verification checks `/health`, `/ready`, and the expected Railway networking variables when supplied in the environment.

## Important separation

`deploy/provision.sh` runs on the operator's machine/CI and talks to Railway's control plane.

`scripts/start.sh` runs inside the container and consumes the values Railway has already generated.

This separation is intentional: a container cannot safely create its own Railway public domain or TCP proxy after it has already started. Provisioning belongs to Railway CLI/API; runtime discovery belongs to the application.

## Security

Never commit:

- `RAILWAY_API_TOKEN`
- Railway project/service/environment tokens
- UUIDs or REALITY private keys
- subscription tokens
- `/data` runtime files
