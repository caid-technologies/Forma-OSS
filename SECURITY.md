# Security Policy

## Project Status and Supported Versions

Forma is currently an alpha-stage research prototype and does not yet have a stable release line. Until stable versions are published, security fixes are applied only to the latest commit on `main`.

| Version or branch | Security support |
| --- | --- |
| Latest `main` | Supported |
| `dev`, `staging`, and feature branches | No guaranteed support |
| Older commits, forks, and modified deployments | Not supported |

This table will be updated when Forma begins publishing stable releases with defined support windows.

## Reporting a Vulnerability

Do not report suspected vulnerabilities in a public issue, discussion, pull request, or other public channel.

Email reports privately to [team@caid-technologies.com](mailto:team@caid-technologies.com) with the subject:

```text
[SECURITY] Forma vulnerability report
```

Include as much of the following as possible:

- A description of the vulnerability and its potential impact
- The affected component, endpoint, workflow, or dependency
- The affected commit, version, and deployment type
- Reproduction steps or a minimal proof of concept
- Required configuration, permissions, or user interaction
- Relevant redacted logs, requests, responses, or screenshots
- Any suggested remediation or mitigation
- Your preferred contact information and disclosure expectations

Never send active credentials, API keys, access tokens, private user data, or unrelated project data. Replace secrets with clearly marked placeholders and minimize any personal information included in the report.

For ordinary bugs, feature requests, and usage questions, use the repository's public issue forms or GitHub Discussions instead.

## What to Expect

Maintainers will make a reasonable effort to:

1. Acknowledge the report and request missing information.
2. Reproduce the issue and assess its severity and affected versions.
3. Develop and verify a fix or mitigation when the report is accepted.
4. Coordinate release and public disclosure with the reporter.
5. Credit the reporter when requested and appropriate.

Forma is maintained as an open-source alpha project and does not currently guarantee a response or remediation service-level agreement. If a report has not been acknowledged after seven calendar days, send a follow-up to the same address.

Please keep the report confidential until maintainers confirm that a fix is available or agree to a disclosure timeline. Maintainers may publish a GitHub Security Advisory and request a CVE when appropriate.

## Scope

Security reports may include, but are not limited to:

- Authentication or authorization bypasses
- Cross-user, cross-project, or cross-organization data exposure
- Credential, token, or encrypted-secret disclosure
- Injection, remote code execution, path traversal, or server-side request forgery
- Unsafe file upload, storage, webhook, or provider-integration behavior
- Vulnerable dependencies with a demonstrated impact on Forma
- Bypasses of enforced hardware-safety boundaries that could enable materially harmful output

Issues that are generally outside this policy include:

- Provider downtime, rate limits, pricing, or model-quality complaints without a security impact
- Hypothetical dependency concerns without an applicable exploit path
- Social engineering, phishing, or physical attacks against maintainers
- Problems that occur only after disabling security controls or modifying unsupported deployments
- Reports generated solely by automated scanners without enough evidence to reproduce or assess the issue

## Good-Faith Research

When investigating Forma:

- Use accounts, projects, credentials, and data you own or are authorized to test.
- Stop testing and report immediately if you encounter data belonging to someone else.
- Do not retain, copy, alter, or disclose data beyond what is necessary to demonstrate the issue.
- Avoid privacy violations, service disruption, denial of service, and destructive testing.
- Follow applicable laws and the terms of any third-party providers involved.

Good-faith reports that follow this policy help protect Forma and its users. This policy does not authorize testing of third-party systems or data.
