# AI-Cloud / Neocloud Sector Framework

For GPU-cloud / "neocloud" businesses — **CoreWeave (CRWV)**, **Nebius (NBIS)**,
and similar — whose economics are dominated by GPU capex and long-dated capacity
contracts. Standard SaaS and even standard hyperscaler lenses misprice them.

Load this framework when `analyze` classifies a company as `ai_neocloud`, or when
the user mentions GPU capacity, backlog/RPO, or capex intensity.

## What to evaluate (beyond the standard report)

1. **Capex intensity** — capex/revenue, shown separately from FCF-based Rule of 40
   so capex is not counted twice.
2. **Funding runway** — net debt, cash, and the financing mix (debt vs equity vs
   vendor/GPU financing). Buildout is pre-funded; runway is the survival metric.
3. **Backlog / RPO** — remaining performance obligations. Pull from the latest
   filing where yfinance lacks the field; label source, fiscal period and currency.
4. **Utilization & contract quality** — booked vs live GPU capacity, contract
   duration, and customer concentration (a few hyperscaler/anchor tenants is
   common and is itself a risk — cross-reference the risk view).
5. **Dilution** — SBC and equity raises fund growth; the dilution-adjusted score
   avoids over-crediting revenue bought with shares.
6. **Margin trajectory vs guidance** — compare current adjusted-EBITDA margin to
   sourced management guidance. Growth alone is not the story.

## How to present a neocloud verdict

- Lead with the **FCF-based Rule of 40**, FCF margin, capex intensity, and the
  broader EBITDA-to-FCF gap—not the flattering EBITDA score alone.
- State funding runway and the latest sourced capex plan explicitly.
- Frame backlog/RPO as the forward signal, with its source and as-of date.
- Be explicit about what yfinance **cannot** provide (backlog, utilization) so the
  user knows which parts need a filing check.

## Data caveats

yfinance exposes income/cashflow/balance-sheet basics but generally **not** RPO,
GPU counts, or utilization. Treat those as "verify in the latest 10-Q/press
release" items and never fabricate them — say "not available from the data
source" instead.
