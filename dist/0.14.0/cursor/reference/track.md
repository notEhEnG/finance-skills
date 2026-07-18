# Workflow — track

Save a company research state.

Run:

```bash
python3 -m finance_skills snapshot create --ticker <TICKER> --format json
```

Create an immutable snapshot, thesis, bull and bear cases, core assumption,
valuation condition, disconfirming conditions, watchpoints, data limitations,
and evidence paths. Write only inside `.finance/companies/<TICKER>/`.

Response:

1. What was saved
2. Current thesis
3. Watchpoints
4. Snapshot period
5. Recommend `/finance refresh <TICKER>`
