# Forma BYOK Provider Policy

Last reviewed: July 20, 2026

This policy controls which provider credentials Forma Cloud may accept from users. It is a conservative product policy, not a formal legal opinion.

## Provider Registry

| Provider | Hosted BYOK | Local BYOK | Self-hosted BYOK | Cloud rule |
| --- | --- | --- | --- | --- |
| OpenAI | Disabled | Enabled | Enabled | Forma Cloud uses a CAID-owned/platform-managed key. Do not accept or store user OpenAI API keys. |
| Anthropic / Claude | Conditional | Enabled | Enabled | Accept only Anthropic Console API keys. Do not accept Claude.ai credentials, cookies, subscription tokens, or unofficial OAuth credentials. |
| Baseten | Enabled | Enabled | Enabled | Require team keys with inference-only permissions and environment scoping. Prefer model scoping. |
| GMI Cloud | Conditional | Enabled | Enabled | Hosted BYOK requires explicit key-delegation acknowledgement and an organization/project-specific key. Production inference and output storage are allowed when model license, retention, and data terms are reviewed; sensitive serverless workloads are restricted by default. |
| Hugging Face | Enabled | Enabled | Enabled | Supports text and image inference through a fine-grained token with only Make calls to Inference Providers, or an enterprise service-account token with equivalent scope. Broad tokens are not accepted. |
| Together AI | Enabled | Enabled | Enabled | Image BYOK requires a project-scoped key dedicated to Forma. Legacy or broad account keys are not accepted; model-specific terms must be enforced and model IDs recorded for stored outputs. |
| NVIDIA Build | Disabled | Enabled | Enabled | Do not accept user-supplied NVIDIA Build/API Catalog keys in Forma Cloud. Free hosted endpoints are trial/evaluation endpoints; production/customer-facing use requires a paid NVIDIA or authorized-provider agreement and reviewed service credentials. |
| Generic image provider | Disabled | Enabled | Enabled | Hosted image BYOK defaults to disabled until the provider terms and credential scopes are reviewed. |

## Shared Hosted BYOK Controls

- Never place provider keys in browser JavaScript, frontend env vars, local storage, logs, analytics, or error tracking.
- Store hosted BYOK credentials only as encrypted backend secrets.
- Display only masked key identifiers after save.
- Use a saved key only for requests initiated by its owning Forma account.
- Provide delete and replace controls.
- Do not use a user key for internal testing, other customers, or background usage without a user request.
- Default new hosted providers to `hosted_byok: disabled` until provider terms and credential docs are reviewed.

## Implementation Notes

- Per-user hosted BYOK is stored in encrypted Supabase `user_integration_configs`.
- Workspace/server-owned provider defaults are stored in encrypted Supabase `workspace_integration_configs`.
- `BLUEPRINT_USER_SECRETS_KEY` encrypts per-user BYOK.
- `BLUEPRINT_WORKSPACE_SECRETS_KEY` encrypts workspace defaults.
- OpenAI API key writes are rejected for hosted per-user Supabase stores; local and self-hosted file-backed stores may still read local OpenAI keys.
- Generic image API key writes are rejected for hosted per-user Supabase stores by default; local and self-hosted file-backed stores may still use compatible image endpoints.
- Hugging Face hosted BYOK token writes require confirmation that the token is fine-grained inference-only or an equivalent enterprise service-account token.
- Hugging Face image BYOK uses the Hugging Face integration token, not the generic image-provider secret field.
- When storing Hugging Face text or image outputs, record model ID, revision when available, inference provider, and model license. Gated models must remain disabled unless the specific user token has access, terms are accepted, and the model/provider terms allow the requested output use.
- GMI Cloud hosted BYOK is conditional. User-supplied hosted keys require explicit confirmation that third-party server-side key delegation is permitted and that the key is scoped to a dedicated project or organization. Platform-managed GMI keys may be used for Forma-managed cloud inference.
- GMI Cloud inference output storage is allowed when Forma stores prompt, output, model ID, endpoint type, request ID, token usage, and creation time for service operation under the user's retained ownership. Model-specific commercial-use, distribution, and storage restrictions still require validation.
- GMI Cloud serverless should be treated as restricted for proprietary hardware schematics, unpublished inventions, customer BOMs, confidential design files, and similar sensitive workloads unless retention period, no-training commitment, data-processing agreement, deletion terms, and data region have been reviewed. Dedicated endpoints or zero-retention arrangements are preferred for sensitive workloads.
- Together AI hosted image BYOK is enabled only for project-scoped API keys dedicated to Forma. Legacy keys and broad account keys are not accepted.
- Together AI credentials must be encrypted at rest, stored backend-only, and should be created with an expiration date where available. Stored image outputs must record the model ID, and model-specific license, usage, distribution, and storage terms must be enforced.
- NVIDIA Build hosted BYOK is disabled. Local development may use NVIDIA Build credentials for experimentation, internal testing, model evaluation, and prototype development by the account holder. Production/customer-facing use is disabled by default and may only be enabled when a paid NVIDIA or service-provider subscription, applicable product agreement, customer-facing application rights, credential scope, data terms, model license, output storage rights, and distribution rights have been reviewed.
- Preferred production NVIDIA paths are customer self-hosted NVIDIA NIM, a paid NVIDIA cloud function with a service key, or an NVIDIA-authorized hosting partner.
