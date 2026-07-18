# Workflow — stress

Run explicit operating and valuation scenarios.

Collect or use explicit assumptions for revenue growth, margin, valuation
multiple, dilution, cash or debt, and time horizon.

Run:

```bash
python3 -m finance_skills stress --ticker <TICKER> --assumptions <JSON> --format json
```

Response:

1. Assumptions
2. Base scenario
3. Upside scenario
4. Downside scenario
5. Highest-sensitivity variable
6. Conditions required
7. Limitations

Distinguish reported values from assumptions, show every assumption, do not call
scenarios forecasts, do not recreate unsupported DCF output, and do not
recommend a trade.
