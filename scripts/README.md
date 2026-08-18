# Repository Scripts

Run scripts from the repository root. They are grouped by the concern they operate on:

- `continuous/` — JSONL stream utilities, continuous agents, and queued LLM jobs.
- `development/` — local backend/frontend development launchers and log helpers.
- `media/` — terminal dashboards, image display, and mechanical video rendering.
- `models/` — provider verification, smoke tests, and comparative model samples.
- `operations/` — production configuration, Supabase maintenance, and artifact uploads.
- `quality/` — deterministic tests, Rust checks, and performance benchmarks.

Common entrypoints:

```bash
./scripts/development/dev.sh
./scripts/quality/test.sh
./scripts/models/verify-llm-providers.py --list
./scripts/quality/benchmark.sh
```

Scripts should stay thin and call reusable implementations from `blueprint_core` or `evals` instead of accumulating application logic.
