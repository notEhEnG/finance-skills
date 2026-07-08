# Segment-Aware Rule of 40

The classic Rule of 40 (revenue growth % + profit margin % ≥ 40) assumes steady
15–30% growth and stable margins. It breaks on companies that don't fit that
mould — most visibly AI neoclouds like **CoreWeave (CRWV)** and **Nebius (NBIS)**,
whose triple-digit growth plus enormous GPU capex produce scores that are either
wildly flattering (EBITDA-based) or brutally negative (FCF-based) depending on
which margin you plug in.

The engine (`scripts/metrics.py::rule40_report`) fixes this by classifying the
company first, then choosing the right lens and benchmark.

## Why one formula doesn't fit all

The 2026 B2B SaaS **median Rule 40 is ~28%** (top quartile ~52%), calculated on
**FCF margin, not EBITDA**, because FCF captures real unit economics that EBITDA
adjustments hide.

| Segment | Typical growth | Right margin | Realistic bar | Example |
|---|---|---|---|---|
| Early-stage (sub-$1M ARR) | high, volatile | FCF | ~18% (deep-negative FCF expected) | seed startups |
| Growth-stage ($10M–$100M ARR) | 20–40% | FCF | 31–38% | median B2B SaaS |
| Mature/public ($100M+ ARR) | 10–20% | FCF | ~42% | top-quartile public SaaS |
| AI neocloud (CRWV, NBIS) | 100–700% | Adjusted EBITDA **+ separate capex check** | score often >100 but misleading alone | CoreWeave: 112% + 56% EBITDA = 168 |

**Nebius illustrates the trap:** ~684% YoY growth with only ~13% adjusted EBITDA
margin nets a Rule 40 near **700** by the EBITDA formula — yet the company guided
to a 40% EBITDA-margin target and $20–25B of 2026 capex, so the score hides how
capital-intensive the growth is.

## The regime classifier

From yfinance-derived signals:
- **AI neocloud** — YoY revenue growth > 100% **and** capex/revenue > 30%.
- **Hypergrowth** — growth > 100% without heavy capex.
- **Early-stage** — revenue < ~$1M.
- **Steady** — everything else.

## What the engine outputs

1. **Dual-margin score** — Rule 40 computed twice, on EBITDA margin and on FCF
   margin. The delta is the **capital-intensity gap**; a large gap (e.g. Nebius's
   ~697 vs ~234 ≈ 463 pts) signals capex-funded growth, not organic profitability.
2. **Capex-adjusted score** — `FCF-based score − capex/revenue`, the "true burn"
   lens for GPU-cloud names.
3. **Dilution-adjusted score** — subtracts share-count growth so revenue "bought"
   with equity (common in hypergrowth AI names via SBC) isn't over-credited.
4. **Preferred score** — the one to judge on, chosen by regime (neocloud →
   capex-adjusted; others → FCF-based).
5. **Stage/sector benchmark** — compares against a matched bar (18% sub-$1M ARR →
   42% mature; sector medians: AI/ML SaaS 38%, DevTools 34%, Cybersecurity 21%,
   FinTech 22%) rather than a flat 40.

## Analyst guidance

- Never quote the EBITDA-based neocloud score alone — always pair it with the
  capex-adjusted score and the gap.
- Prefer **percentile vs stage-matched peers** over a pass/fail flag.
- Add **trend context**: median B2B SaaS Rule 40 fell from 41% (2022) to 28%
  (2026), so a single-quarter score without a trajectory can mislead.
- For neoclouds, overlay **backlog/RPO** (CoreWeave's backlog approached ~$100B in
  Q1 2026) as a stronger forward signal than trailing growth — see
  [`ai-cloud.md`](ai-cloud.md).
