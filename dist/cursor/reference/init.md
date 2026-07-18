# Workflow — init

Create safe project-level research context.

1. Inspect existing `RESEARCH.md` and `.finance/config.json`.
2. Preserve valid existing content.
3. Do not ask for portfolio size, wealth, income, or risk tolerance.
4. Use non-sensitive defaults when context is absent.
5. Write only `RESEARCH.md` and `.finance/config.json`.
6. Stop if paths resolve outside the project.

Run:

```bash
python3 -m finance_skills context init --format json
```

Default configuration:

- US public equities
- USD reporting currency
- fundamentals-first research
- standard depth
- filings before investor relations before market data
- no personalized trading instructions
- no automatic price targets

Response:

1. files created or preserved;
2. research defaults;
3. how to edit `RESEARCH.md`;
4. recommend `/finance screen <ticker>`.
