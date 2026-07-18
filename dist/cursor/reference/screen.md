# Workflow — screen

Produce a fast, evidence-grounded company assessment.

Run:

```bash
python3 -m finance_skills screen --ticker <TICKER> --format json
```

Use only report values. Analyze revenue growth, profitability, free-cash-flow
conversion, capital intensity, dilution, balance sheet, valuation basis,
important detector findings, and data limitations.

Response order:

1. Bottom line
2. Key metrics
3. What is working
4. What is concerning
5. Valuation context
6. Limitations
7. Conditional conclusion

Rules:

- Do not call a company cheap or expensive without a comparison basis.
- Do not manually calculate missing metrics.
- Do not hide negative or conflicting evidence.
- Recommend at most one next command.
