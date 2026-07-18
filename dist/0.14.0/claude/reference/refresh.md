# Workflow — refresh

Compare current company data with saved research.

Run:

```bash
python3 -m finance_skills diff --ticker <TICKER> --format json
```

Read the previous thesis and snapshot, current report, open watchpoints, and
deterministic diff.

Response:

1. What changed
2. Material improvements
3. Material deteriorations
4. Triggered or resolved watchpoints
5. Thesis status
6. Reason
7. Proposed thesis revision
8. Remaining uncertainty

Allowed thesis states are `STRENGTHENED`, `UNCHANGED`, `WEAKENED`, `BROKEN`,
and `INCONCLUSIVE`. Do not overwrite thesis wording without showing the proposed
update.
