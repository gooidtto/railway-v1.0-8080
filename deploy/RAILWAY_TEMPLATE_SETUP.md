# Railway Template Setup

This repository is prepared to be used as a Railway Template, but the Template itself is created in the Railway workspace UI. Railway does not currently support importing a `template.json` file or creating a Template through a public template-management API.

## One-time maintainer setup

1. Deploy the `railway-v1.0-8080-portable` branch once to a Railway project.
2. Confirm the service starts and `/health` and `/ready` work.
3. In the Railway project, use **Settings → Generate Template from Project**.
4. In the Template Composer, keep the service source pointed at this repository and the `railway-v1.0-8080-portable` branch. Railway supports specifying a branch by using the full GitHub branch URL as the source.
5. Configure the service for:
   - Dockerfile build from the repository root.
   - Gateway target/application port: `8080`.
   - Public Networking enabled.
   - TCP Proxy enabled with application/target port `8080`.
   - Healthcheck path: `/health`.
   - Railway Volume mounted at `/data`.
6. Create the Template and copy the Template URL supplied by Railway.
7. Replace the temporary GitHub deploy button in the README with the Railway Template deploy button using that URL.

## Important dynamic values

Do not put any deployment-specific values into the Template source:

- no `*.up.railway.app` hostname
- no `*.proxy.rlwy.net` hostname
- no fixed TCP Proxy external port such as `42827`

At runtime the service discovers:

```text
RAILWAY_PUBLIC_DOMAIN
RAILWAY_TCP_PROXY_DOMAIN
RAILWAY_TCP_PROXY_PORT
RAILWAY_TCP_APPLICATION_PORT
PORT
```

The TCP Proxy application/target port remains `8080`; Railway generates the external TCP Proxy hostname and external port for each deployment.

## Expected end-user flow

```text
README
  ↓
Deploy on Railway
  ↓
Railway login / account creation
  ↓
Template configuration / confirmation
  ↓
Deploy
  ↓
New Railway project
  ↓
Service + volume + public networking + TCP proxy
```

The Template deployment flow is preferable to the generic GitHub repository picker because the Template stores the service source and infrastructure configuration. Railway documents that Template services deploy directly from the defined source and that Templates can configure variables, public networking/TCP Proxy, healthchecks, volumes, and a specific GitHub branch.
