# Railway Template Setup

This branch is prepared for a Railway Template. The Template itself is a Railway workspace resource, so the final Template URL must be created in the Railway dashboard by the repository owner/maintainer.

## Target end-user flow

The final README button must point to the real Railway Template URL:

```text
README
  ↓
🚀 Deploy on Railway
  ↓
Railway Template
  ↓
Login / Sign up if required
  ↓
Review the Template deployment configuration
  ↓
Deploy
  ↓
New Railway Project + Service
  ↓
Build
  ↓
Start
```

Railway documents that Template deployment uses the services and source defined by the Template, then creates a new project and starts the deployment. This avoids the generic GitHub repository picker. See: https://docs.railway.com/templates/deploy

## One-time maintainer action in Railway

1. Open Railway and create/use the project that will be used as the Template source.
2. Deploy this repository's `railway-v1.0-8080-portable` branch to that project/service.
3. Confirm the service starts successfully.
4. Verify `/health` and `/ready` before publishing the Template.
5. From Railway's Template/project tooling, create a Template from the configured project/service.
6. In the Template configuration, verify the service source points to this repository and the intended portable branch.
7. Keep the service's Dockerfile/build configuration at the repository root.
8. Configure the service's intended application target as `8080`.
9. Configure the Railway TCP Proxy target/application port as `8080`.
10. Configure the `/health` healthcheck.
11. Configure the Railway Volume mount at `/data`.
12. Do not enter any deployment-specific public hostname or TCP external port.
13. Publish/create the Template.
14. Copy the real Template Deploy URL supplied by Railway.
15. Replace the temporary generic GitHub button in the root README with Railway's official Template Deploy button/URL.

Railway's current documentation confirms that Templates are pre-configured groups of services and that deploying a Template creates a new project with the defined services. See: https://docs.railway.com/templates/deploy

## Template networking rules

The Template must not contain old instance-specific values such as:

```text
*.up.railway.app
*.proxy.rlwy.net
42827
```

The only fixed networking target is:

```text
TCP application/target port = 8080
```

At runtime Railway supplies the deployment-specific values:

```text
RAILWAY_PUBLIC_DOMAIN
RAILWAY_TCP_PROXY_DOMAIN
RAILWAY_TCP_PROXY_PORT
RAILWAY_TCP_APPLICATION_PORT
PORT
```

The external TCP Proxy hostname and external port are generated for the current Railway deployment. They must never be copied from an earlier account/project.

## Template source and updates

The service should remain connected to the GitHub source used by this Template. Railway supports templates based on GitHub repositories and can notify template consumers when upstream changes are available.

For this portable branch, do not promote changes to the production `main` branch merely to make Template deployment work. Keep the portable deployment baseline isolated until a fresh Railway deployment has passed the complete validation checklist.

## Final README button

Do not invent a Template URL.

Before the Template exists, the README may retain the generic GitHub deployment link only as a clearly labelled fallback.

After Railway creates the Template, replace that fallback with the exact URL Railway provides, for example:

```text
https://railway.com/deploy/<REAL-TEMPLATE-ID-OR-SLUG>
```

The placeholder above is documentation only. It must not be committed as the final button URL.

## Final validation after publishing the Template

Deploy the Template from a separate Railway account/project and verify, in order:

```text
1. Template page opens
2. Login/sign-up works
3. Template configuration is shown
4. Deploy creates a NEW Railway Project
5. Service build starts
6. Container starts
7. /health returns 200
8. /ready returns 200
9. Railway generates the current public domain
10. TCP Proxy target is 8080
11. Railway generates the current TCP Proxy external domain/port
12. Primary subscription uses the current public domain
13. Fallback subscription uses the current TCP Proxy domain + current random external port
14. HTTPS/XHTTP node works
15. REALITY/XHTTP nodes work
```

Do not treat a successful Template creation or Docker build as proof of a working runtime. The Template, build, networking, and client paths must all be validated separately.
