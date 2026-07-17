# Developer API Testing

Use these checks to verify API-key authentication, provider discovery, runtime provider/model selection, asynchronous job creation, and polling.

## Automated Route Tests

Run the developer API route suite from the repository root:

```bash
./.venv/bin/python -m unittest tests.test_developer_api_surface -v
```

The suite includes:

- A real offline `simulation` generation through `POST /api/v1/jobs`, followed by `GET /api/v1/jobs/{job_id}` polling.
- HTTP request parsing, dependency wiring, response status, and persisted job-state checks.
- Explicit Baseten/GLM and OpenAI provider/model routing checks. These mock only the outbound generation boundary, so automated tests do not use provider credits or require network access.
- A `/api/v1/llms` check proving configured provider and model choices are returned to API clients.

## Test Configuration

Set the API URL and a Blueprint user API key. Do not use a provider credential such as `BASETEN_API_KEY` as the Blueprint API key.

```bash
export BLUEPRINT_API_BASE_URL="http://127.0.0.1:8000/api/v1"
export BLUEPRINT_API_KEY="bp_live_replace_me"
```

Verify authentication:

```bash
curl --fail-with-body --silent --show-error \
  "$BLUEPRINT_API_BASE_URL/me" \
  -H "Authorization: Bearer $BLUEPRINT_API_KEY"
```

## Discover Available Providers and Models

Always query the running deployment before choosing a provider or model:

```bash
curl --fail-with-body --silent --show-error \
  "$BLUEPRINT_API_BASE_URL/llms" \
  -H "Authorization: Bearer $BLUEPRINT_API_KEY"
```

Only submit combinations returned in a provider's `models` array. Availability is controlled by `LLM_ALLOWED_PROVIDERS` and the provider-specific `*_ALLOWED_MODELS` variables.

## Real Simulation Test

Simulation runs the actual Blueprint pipeline without calling an external LLM. The deployment must allow the `simulation` provider.

```bash
curl --fail-with-body --silent --show-error \
  "$BLUEPRINT_API_BASE_URL/jobs" \
  -H "Authorization: Bearer $BLUEPRINT_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{
    "prompt": "A USB-powered LED continuity tester with a push button",
    "workflow": "default",
    "provider": "simulation",
    "model": "simulation",
    "generate_image": false
  }'
```

The API returns `202 Accepted` with a `job_id` and `poll_url`. Poll the returned URL until `status` is `succeeded` or `failed`:

```bash
export JOB_ID="job_api_replace_me"

curl --fail-with-body --silent --show-error \
  "$BLUEPRINT_API_BASE_URL/jobs/$JOB_ID" \
  -H "Authorization: Bearer $BLUEPRINT_API_KEY"
```

## Live Baseten GLM Test

This is a real provider call and may consume credits. The backend deployment needs `BASETEN_API_KEY`, and its runtime allowlists must include `baseten` and `zai-org/GLM-5.2`.

```bash
curl --fail-with-body --silent --show-error \
  "$BLUEPRINT_API_BASE_URL/jobs" \
  -H "Authorization: Bearer $BLUEPRINT_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{
    "prompt": "A compact USB-C powered LED tester with a button and status indicator",
    "workflow": "default",
    "provider": "baseten",
    "model": "zai-org/GLM-5.2",
    "generate_image": false
  }'
```

Poll the returned `job_id` with the same command used for simulation. A successful job reports the selected `provider` and `model` in its job payload.

## Test Another Provider or Model

Take an exact provider/model pair from `/llms` and change only these request fields:

```json
{
  "provider": "openai",
  "model": "gpt-5.5"
}
```

The backend, not the client, owns provider credentials. A Blueprint API user can select only deployment-enabled choices and never receives the underlying provider secret.

To verify allowlist enforcement, submit a model that is not listed by `/llms`. The API should return `400 Bad Request` with `llm_config_invalid`; it must not silently switch to another live model.

## List Test Jobs

List jobs created by the current key:

```bash
curl --fail-with-body --silent --show-error \
  "$BLUEPRINT_API_BASE_URL/jobs?limit=20" \
  -H "Authorization: Bearer $BLUEPRINT_API_KEY"
```

Use `?scope=owner&limit=20` to include jobs created by other API keys belonging to the same user.
