# Redesigned engine contract

The existing `analyze.build_report` calculations remain canonical. The redesign
projects those calculations into `evidence-report.schema.json`; it does not
recompute them in workflow prompts.

## Current deterministic calculations

- Year-over-year revenue growth
- Gross, EBITDA, and free-cash-flow margins
- Capital-expenditure intensity
- Share-count dilution
- Net debt and enterprise value
- EV/sales and EV/EBITDA
- Dual-margin Rule of 40 with project-authored reference bands
- Explicit-assumption DCF helpers, disabled in automatic company workflows

Every redesigned derived metric records its formula, observation input paths,
period alignment, currency alignment, and calculation version. Project-authored
reference bands and scenario deltas are labelled and cannot independently prove
that a company is cheap or expensive.

## State compatibility

State schema `1.0` is creation-only. Immutable history is authoritative. Under
the repository no-overwrite policy, `latest-snapshot.json` is created for the
first snapshot and is not replaced; context and refresh derive the current
snapshot from immutable history.

## Fixture policy

Fixtures require an explicit `--fixture` flag in every redesigned CLI workflow.
Provider failure never substitutes fixture data automatically.

## Provider orchestration

Historical evidence is loaded in priority order: coherent SEC filing cohorts,
project-local investor-relations disclosures, then approved market data. Matching
values reconcile at a 1% relative tolerance. Material value differences and all
period or currency differences remain visible in `reconciliation_conflicts`;
they are never averaged.

SEC access requires `FINANCE_SEC_USER_AGENT` with a contact email. IR disclosures
are read only from
`.finance/companies/TICKER/providers/investor-relations.json`; source references
are treated as data and are never fetched. Estimates require
`--include-estimates` or `providers.estimates.enabled`, remain under
`estimate_observations`, and never replace reported historical values.
