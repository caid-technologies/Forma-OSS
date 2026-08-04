# Cloudflare backend deployment

Forma keeps the FastAPI application in its existing Docker image. A small
Worker routes HTTP and WebSocket requests to one named Cloudflare Container:

```text
Browser -> forma-api Worker -> FormaApiContainer -> Uvicorn/FastAPI
                                                -> Supabase, Redis, providers
```

The production URL is `https://forma-api.caid.workers.dev`. The frontend reads
`NEXT_PUBLIC_API_URL` first and uses that URL as its production fallback. Local
Next.js development continues to use `http://localhost:8000`.

## Provisioned resources and lifecycle

The configuration in `apps/api/wrangler.jsonc` declares:

- Worker: `forma-api` in the `Caid` Cloudflare account.
- Container application: `forma-api-container` using the repository-root build
  context and `apps/api/Dockerfile`.
- One `standard-1` instance maximum and one named Durable Object instance.
- Port `8000`, outbound internet access, and a 15-minute idle sleep timeout.
- Workers logs and sampled traces.

Cloudflare Containers require the Workers Paid plan. Docker must also be
running for local development and deployment because Wrangler builds and
pushes the image.

The single instance is intentional for the initial deployment. Durable
application state is external; the Durable Object only controls Container
routing and lifecycle. Increase `max_instances` and switch to explicit load
balancing only after verifying that all request coordination is safe across
multiple processes.

## Runtime configuration

Non-secret production controls are committed in `wrangler.jsonc`. Sensitive
and environment-specific settings are stored in one encrypted Worker secret,
`FORMA_BACKEND_ENV`, then expanded into Container environment variables by the
Worker. The sync script accepts only an explicit allowlist and never uploads
`CLOUDFLARE_API_TOKEN`, Vercel credentials, or unrelated shell variables.

Required secret values are:

- `BLUEPRINT_USER_SECRETS_KEY`
- `CLERK_SECRET_KEY`
- `NEXT_PUBLIC_CLERK_PUBLISHABLE_KEY` (public to browsers, but bundled with the
  server configuration for atomic setup)
- `REDIS_URL`
- `SUPABASE_URL`
- `SUPABASE_SERVICE_ROLE_KEY`

The allowlist also supports the configured model, image, research, object
storage, admin, and Langfuse settings shown in `apps/api/.env.example`. Provider
keys are optional when every user supplies an encrypted BYOK integration.

Production uses `DATABASE_BACKEND=supabase`; job metadata therefore uses the
same Supabase database. Project data, jobs, integration settings, and images do
not depend on Container memory or disk. The filesystem may only hold temporary
request data. `REDIS_URL` must point to an externally hosted, TLS-enabled Redis
service rather than `localhost`.

Supabase startup calls only select each required table to validate schema. It
does not run DDL migrations. If the component template table is empty, the
existing idempotent seed routine inserts missing templates. Apply SQL migrations
from `supabase/` separately before deployment.

## Local Docker validation

From the repository root:

```bash
docker info
docker build --platform linux/amd64 -f apps/api/Dockerfile -t forma-backend:local .
docker run --rm --name forma-backend-local \
  --env-file .env \
  -e BLUEPRINT_AUTH_MODE=local \
  -e BLUEPRINT_DEV_MODE=true \
  -e DATABASE_BACKEND=sqlite \
  -e PROJECT_PURGE_WORKER_ENABLED=false \
  -p 8000:8000 \
  forma-backend:local
```

In another terminal:

```bash
curl --fail --silent http://localhost:8000/health
curl --fail --silent http://localhost:8000/api/health
```

The response is `{"status":"healthy"}`. This endpoint does not call the
database or a model provider. To exercise the Worker and Container together,
create an ignored `apps/api/.dev.vars` containing a valid JSON
`FORMA_BACKEND_ENV`, then run `npm run dev:cloudflare` from `apps/api`.

## Deploy

From `apps/api`:

```bash
npm ci
npm run typecheck
npm run secrets:sync -- --check ../../.env ../../.env.production.local
npm run deploy:cloudflare
npm run secrets:sync -- ../../.env ../../.env.production.local
npx wrangler containers list
```

The first deployment provisions the Worker, Container application, image, and
Durable Object. Upload the secret before sending the first request. `secret put`
creates a new Worker version after the Worker exists. If environment values are
changed later, sync the secret and force a Container restart with a normal
deployment so the next start receives the new values.

Do not commit `.env`, `.env.production.local`, or `.dev.vars`. Cloudflare's
dashboard should show only `FORMA_BACKEND_ENV` as an encrypted secret; its value
cannot be read back.

## Production verification

Wait until `npx wrangler containers list` reports a ready deployment, then run:

```bash
export FORMA_API_URL=https://forma-api.caid.workers.dev
curl --fail --silent "$FORMA_API_URL/health"
curl --fail --silent "$FORMA_API_URL/api/health"
curl --include --request OPTIONS "$FORMA_API_URL/my/projects" \
  --header 'Origin: https://caid-technologies.us' \
  --header 'Access-Control-Request-Method: GET' \
  --header 'Access-Control-Request-Headers: authorization'
```

Use a short-lived Clerk session token without saving it to shell history for
authenticated checks:

```bash
read -rsp 'Clerk bearer token: ' CLERK_TOKEN
curl --fail --silent "$FORMA_API_URL/my/projects" \
  --header "Authorization: Bearer $CLERK_TOKEN"
```

For the authenticated write check, patch a project owned by the same user. For
the representative generation check, submit the same payload used by the web
composer to `POST /generate` with the bearer token, then confirm its job record
appears through the jobs API. Avoid putting tokens or prompts containing private
data in CI logs.

In browser developer tools verify that requests target the Forma API URL,
contain the Clerk `Authorization` header, have no CORS errors, and return JSON
errors. CORS permits only the four committed Forma HTTPS origins plus localhost
and `127.0.0.1`; unrelated origins receive no allow-origin header.

Use `npx wrangler tail forma-api` and the Containers dashboard for startup,
shutdown, application, and request errors. The Worker returns a structured 503
when the Container is temporarily unavailable during a cold start or rollout.

## Long-running work and shutdown

`POST /generate`, A2A generation, project iteration, image/video generation,
and video correction can run for several minutes. Their metadata is persisted
in the primary Supabase database, but execution still occurs inside the HTTP
request or Container process. An infrastructure restart can interrupt active
work even though its last recorded status survives.

Cloudflare deployment disables the existing in-process project-retention purge
loop because a scale-to-zero web process is not a reliable scheduler. A follow-up
must move retention purges and long generation work to this durable pattern:

```text
API request -> persisted job -> Cloudflare Queue/Workflow -> Container consumer
            -> persisted progress -> frontend polling or streaming
```

Until that follow-up lands, do not treat the Container as an indefinitely
running worker, and run due retention purges from an external authenticated
scheduled process. The A2A raw TCP port is not publicly exposed; REST, MCP, and
WebSocket routes through Uvicorn remain available on port 8000.

Uvicorn receives `SIGTERM` during sleep or rollout. FastAPI stops the A2A server,
stops any enabled purge task, and flushes observability before exit. Cloudflare
allows up to 15 minutes before force-killing a Container, while this deployment
uses a 60-second active rollout grace period before shutdown begins.

## Rollback

List Worker versions and recent deployments, then roll back to a known version:

```bash
cd apps/api
npx wrangler versions list
npx wrangler deployments list
npx wrangler rollback <WORKER_VERSION_ID> --message "Rollback Forma API"
```

Worker rollbacks are immediate, while Container image changes roll out
separately. Confirm the deployment and image state with:

```bash
npx wrangler containers list
npx wrangler containers images list
curl --fail --silent https://forma-api.caid.workers.dev/health
```

Do not roll back database schema independently unless the selected application
version explicitly documents a compatible down migration. Keep Worker changes
backward compatible with both Container image versions during a rollout.
