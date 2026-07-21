# Public Launch Document Checklist

This checklist tracks document and policy work before Blueprint is published as a public-facing hosted application.

## Required Document Review

- [ ] Replace all bracketed placeholders in legal documents.
- [ ] Confirm company legal name, trade name, mailing address, support email, privacy email, security email, abuse email, and safety email.
- [ ] Confirm governing law, dispute venue, and whether to include arbitration or class-action terms.
- [ ] Have counsel review Terms, Privacy Policy, Acceptable Use Policy, safety disclaimer, DMCA policy, and cookie notice.
- [ ] Decide whether the hosted app, open-source repo, and API need separate terms.
- [ ] Add a repository license if the project is intended to be open source.

## Product and Data Mapping

- [ ] Inventory collected data: accounts, prompts, uploads, chat history, project outputs, logs, API keys, analytics, and payments.
- [ ] List vendors and subprocessors: hosting, Supabase/database, model providers, image providers, auth, analytics, email, payments, storage, observability, and support.
- [ ] Confirm whether prompts, images, and outputs are retained by each AI provider.
- [ ] Confirm deletion/export behavior for accounts, projects, logs, backups, and provider-side data.
- [ ] Decide whether user content may be used for model evaluation, fine-tuning, examples, or marketing.
- [ ] Add a consent flow for any non-essential cookies, analytics, or marketing tools where required.
- [ ] Confirm BYOK/API-key storage uses encrypted Supabase `user_integration_configs`, server-only `BLUEPRINT_USER_SECRETS_KEY`, and no plaintext credential columns or logs.
- [ ] Confirm Supabase plan, DPA, subprocessor list, data residency, retention, and backup deletion posture for the jurisdictions where the app is offered.
- [ ] For HIPAA/PHI workloads, execute a Supabase BAA and enable the required HIPAA environment controls before allowing PHI. If no BAA is in place, prohibit PHI in product copy and policy.

## Public App Requirements

- [ ] Link Terms, Privacy Policy, Acceptable Use, Safety Disclaimer, and Cookie Notice from the app footer or account/signup flow.
- [ ] Require acceptance of Terms before account creation or first hosted generation.
- [ ] Add an age statement or age gate if the Service may attract minors.
- [ ] Add an in-product safety warning before users rely on generated hardware outputs.
- [ ] Add a privacy request path for access, deletion, export, correction, and opt-out requests.
- [ ] Add unsubscribe links and sender information to marketing emails.
- [ ] Publish a security contact and route reports to a monitored inbox.
- [ ] Publish a DMCA agent contact if user-generated content is hosted.
- [ ] Add an accessibility contact path and run keyboard/contrast checks before launch.

## Operational Follow-Up

- [ ] Create a vendor/subprocessor list and keep it updated.
- [ ] Set retention defaults for project data, local logs, uploaded images, and generated artifacts.
- [ ] Confirm backup retention and deletion behavior.
- [ ] Create a process for account deletion and project deletion requests.
- [ ] Create an incident response owner and escalation path.
- [ ] Decide whether bug bounty, responsible disclosure, or security.txt should be published.
- [ ] Review export controls, sanctions, product safety, and marketplace/supplier issues before enabling commercial hardware workflows.
