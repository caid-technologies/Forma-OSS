# Forma evaluations

This directory is the shared home for performance benchmarks and output-quality evaluations. Performance measures how reliably and quickly a workflow runs; quality measures whether its result is correct, complete, feasible, and faithful to the request.

```text
evals/
├── performance/  Provider, model, pipeline, and offline timing benchmarks
├── quality/      Correctness and output-quality evaluation suites
├── datasets/     Reusable prompts, fixtures, rubrics, and expected outputs
└── reports/      Optional local or curated evaluation reports
```

## Performance benchmarks

Run the deterministic offline suite from the repository root:

```bash
./scripts/benchmark.sh
./evals/performance/benchmark_offline.py --iterations 1000
```

Inspect configured provider/model pairs without making generation calls:

```bash
./evals/performance/benchmark_models.py --iterations 1
```

Add `--live` to measure real provider calls:

```bash
./evals/performance/benchmark_models.py \
  --live \
  --llm openai/gpt-5.5 \
  --iterations 3 \
  --concurrency 2
```

For compatibility with existing automation, benchmark reports still default to `.logs/benchmarks/`, and their console output, schema, filenames, and Hugging Face artifact layout are unchanged. Pass `--output-dir evals/reports/performance` when a report specifically belongs under this umbrella.

## Quality evaluations

Quality suites belong in `quality/` and should use reusable inputs from `datasets/`. Typical checks include BOM accuracy, component compatibility, wiring correctness, prompt adherence, schema completeness, feasibility, and unsupported-component detection.

Keep evaluation logic separate from production generation code. A quality suite should document its dataset, scoring method, thresholds, and whether it can call paid or networked providers. Deterministic checks should be the default for automated tests; live evaluations must require an explicit flag.

## Extending the suite

1. Put reusable, non-secret inputs and expected outputs in `datasets/`.
2. Add the runner under `performance/` or `quality/` according to what it measures.
3. Write generated output to `.logs/` by default, or to `reports/` when explicitly requested.
4. Add offline regression coverage under `tests/`.
5. Document live-provider requirements, costs, and report fields.

Do not commit credentials, proprietary prompts, or generated reports containing secrets or user data.
