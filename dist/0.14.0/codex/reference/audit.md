# Workflow — audit

Perform a forensic financial-data and accounting review.

Run:

```bash
python3 -m finance_skills audit --ticker <TICKER> --format json
```

Review data provenance, provider-defined metrics, filing reconciliation, period
and currency alignment, working-capital effects, operating cash-flow quality,
capex definition, stock-based compensation, dilution, debt and maturity
completeness, valuation-date alignment, and detector findings.

Response:

1. Audit conclusion
2. High-severity findings
3. Medium-severity findings
4. Data-quality limitations
5. Plausible benign explanations
6. Verification checklist

Preserve detector rule IDs, severity, confidence, evidence, and remediation.
Do not accuse a company of fraud or misconduct without direct evidence.
