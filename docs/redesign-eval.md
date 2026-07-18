# Redesign evaluation protocol

The deterministic validators in `scripts/redesign_eval.py` measure:

- grounded quantitative claims, target ≥95%;
- correct company/metric/period/currency/unit/sign association, target ≥98%;
- preservation of every high/critical finding, target 100%;
- workflow correctness, target 100%.

It also runs the adversarial validators for metric swaps, ticker swaps, period
and currency swaps, sign inversion, unsupported causality, hidden assumptions,
fixture/live mislabelling, and disabled-analysis recreation.

## Transcript matrix

Evaluation fixtures should cover a profitable mature company, hypergrowth
unprofitable company, capital-intensive cloud company, semiconductor, cyclical
industrial, bank/insurer, missing debt, mismatched currency, provider outage,
fixture-only environment, improving tracked company, and thesis-breaking
tracked company.

## Skill-on versus skill-off

For model evaluation:

1. run the prompt without a skill;
2. run it with the compatibility skill;
3. run it with the redesigned skill;
4. randomize transcript order;
5. use blinded reviewers for usefulness, clarity, traceability, conditional
   reasoning, risk balance, and unsupported confidence;
6. publish prompts, rubric, aggregate scores, and model versions.

The repository implements the reproducible harness and rubric. Actual model
runs remain environment-specific and must not be represented as completed
unless their transcripts are published.

`scripts/study_harness.py` adds creation-only study manifests, exact headless
command templates, deterministic transcript randomization, blinded review
packets, and validated human-score aggregation. The v0.14.0 release ships this
harness without executing external model calls. Every adapter therefore reports
its command-contract result separately from model evaluation status, which
remains `unpublished`.
