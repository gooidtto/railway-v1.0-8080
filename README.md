# Portable Railway + Xray XHTTP/REALITY

A portable Railway deployment variant derived from the verified production baseline.

## 🚀 Deploy on Railway

**Portable deployment does not depend on a Railway Template.** Every Railway user/account can deploy this repository independently.

### Recommended flow — Railway GitHub

```text
README
  ↓
🚀 Deploy on Railway
  ↓
Railway login / sign up
  ↓
GitHub authorization
  ↓
Repository picker
  ↓
Select the repository currently being deployed
  ↓
Verify Repository / Source
  ↓
Deploy Repo
  ↓
New Railway Project / Service
  ↓
Build
  ↓
Start
```

Railway's official GitHub deployment flow requires selecting the repository and then starting the deployment. A static GitHub README cannot force Railway's external `/new/github` page to automatically identify the repository that contains the README, so the README does **not** pretend that the generic Railway button is a current-repository auto-selector. citehttps://docs.railway.com/quick-start

### Optional — true zero-selection deployment from the current checkout

If the user has the repository cloned locally, Railway's CLI can deploy the current directory without a GitHub repository picker:

```bash
railway up --new --yes
```

If the user is not signed in, `railway up` opens the Railway sign-in/sign-up flow and then continues the deployment. With `--new --yes`, Railway creates a new Project + Service from the current directory and deploys it. citehttps://docs.railway.com/cli/up

This is the portable branch's **deterministic deployment path** because it deploys the exact checkout the user has, regardless of repository name, owner, or branch name.

---

## Railway networking model

The deployment has one fixed internal Gateway target and dynamic Railway public endpoints:

```text
Fixed inside the application:

Gateway target/application port = 8080

Dynamic per Railway deployment:

RAILWAY_PUBLIC_DOMAIN
RAILWAY_TCP_PROXY_DOMAIN
RAILWAY_TCP_PROXY_PORT
```

The TCP Proxy is created against application/target port `8080`. Railway generates the external proxy domain and external proxy port for the current deployment. The external port is **not fixed**; values such as `42827` belong only to an individual Railway deployment and must never be hard-coded. citehttps://docs.railway.com/networking/tcp-proxy

At runtime the service consumes the current Railway values instead of storing deployment-specific hostnames or ports in the repository.

## Subscription endpoints

The service generates both current-instance subscription endpoints:

```text
PRIMARY
https://<CURRENT-RAILWAY-PUBLIC-DOMAIN>/sub/<CURRENT-TOKEN>

FALLBACK
http://<CURRENT-RAILWAY-TCP-PROXY-DOMAIN>:<CURRENT-RAILWAY-TCP-PROXY-PORT>/sub/<CURRENT-TOKEN>
```

The placeholders above are documentation notation only. They are replaced at runtime with the actual values supplied by the current Railway deployment.

The generated files are stored under `/data`:

```text
subscription_primary_url.txt
subscription_fallback_url.txt
subscription_endpoints.txt
```

The seven REALITY/XHTTP nodes use the current `RAILWAY_TCP_PROXY_DOMAIN` and current `RAILWAY_TCP_PROXY_PORT`.

## Deployment configuration

### Application

```text
Gateway: 0.0.0.0:8080
Xray HTTPS/XHTTP: 127.0.0.1:10086
Xray REALITY/XHTTP: 127.0.0.1:10087
```

### Railway

```text
Application / TCP target: 8080
Volume: /data
Healthcheck: /health
Readiness: /ready
```

Public Domain and TCP Proxy are Railway-side networking resources. The application must use the values Railway supplies for the current instance.

## Runtime discovery

Authoritative runtime variables:

```text
RAILWAY_PUBLIC_DOMAIN
RAILWAY_TCP_PROXY_DOMAIN
RAILWAY_TCP_PROXY_PORT
RAILWAY_TCP_APPLICATION_PORT
PORT
RAILWAY_VOLUME_MOUNT_PATH
```

The startup logic validates that the TCP application target resolves to the fixed Gateway target `8080` and uses the current Railway TCP Proxy domain/port for generated REALITY nodes and fallback subscription URLs.

No old deployment hostname or external TCP port is used as a fallback.

## Deployment helpers

```text
deploy/
├── provision.sh
├── verify.sh
└── README.md
```

`provision.sh` documents/validates the Railway control-plane requirements. `verify.sh` validates that the current deployment exposes the expected runtime values and health endpoints.

These scripts intentionally do not contain a fixed Railway hostname or external TCP port.

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

## Subscription structure

The generated subscription contains **8 nodes**:

1. One HTTPS + TLS + XHTTP node using the current Railway public domain.
2. Seven XHTTP + REALITY nodes using the current Railway TCP Proxy endpoint and verified SNI pool.

## First deployment validation

After deployment, verify in this order:

```text
1. Repository / Source is correct
2. Deploy Repo is confirmed
3. New Railway Project / Service is created
4. Build succeeds
5. Container starts
6. /health returns 200
7. /ready returns 200
8. Startup log shows the current public domain
9. Startup log shows the current TCP Proxy host:port
10. Primary subscription contains the current public domain
11. Fallback subscription contains the current TCP Proxy domain + current random external port
12. Subscription returns 8 nodes
13. HTTPS/XHTTP client test succeeds
14. REALITY/XHTTP client tests succeed
```

Do not treat a successful Docker build as proof of a successful runtime. Build and runtime validation are separate.

## Security / repository hygiene

Never commit:

- UUIDs
- REALITY private keys
- REALITY public keys generated for a deployment
- VLESS encryption/decryption material
- subscription tokens
- `/data` runtime artifacts
- Railway API/project tokens

The repository contains generation logic and the verified SNI pool, not deployment secrets.

## Stability rule

This branch is a **portable deployment variant**, not a replacement for the current production baseline.

Keep changes isolated here until a fresh Railway deployment has passed:

- website test
- `/health`
- `/ready`
- HTTPS/XHTTP client test
- TCP Proxy/REALITY client test
- subscription node-count and hostname validation

Only after those tests pass should the changes be considered for promotion to the production baseline.
