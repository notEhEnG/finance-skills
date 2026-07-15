# Segment-Aware Rule of 40

The classic Rule of 40 (revenue growth % + profit margin % ≥ 40) assumes steady
15–30% growth and stable margins. It breaks on companies that don't fit that
mould — most visibly AI neoclouds like **CoreWeave (CRWV)** and **Nebius (NBIS)**,
whose triple-digit growth plus enormous GPU capex produce scores that are either
wildly flattering (EBITDA-based) or brutally negative (FCF-based) depending on
which margin you plug in.

The engine (`scripts/metrics.py::rule40_report`) fixes this by classifying the
company first, then choosing the right lens and clearly labelled project heuristic.

## Why one formula doesn't fit all

The engine treats Rule of 40 thresholds as **project heuristics**, not cited market
medians. They are screening context, never empirical peer percentiles. FCF margin
is the preferred cash-economics lens because it includes capex and other cash
items that EBITDA excludes.

| Segment | Growth lens | Right margin | Built-in threshold | Validation |
|---|---|---|---|---|
| Early-stage | high, volatile | FCF | project heuristic only | verify against a real peer set |
| Growth-stage | high | FCF | project heuristic only | verify against a real peer set |
| Mature/public | steadier | FCF | project heuristic only | verify against a real peer set |
| AI neocloud | can be triple-digit | FCF **+ separate capex check** | no green pass with negative FCF margin | EBITDA score can mislead |

The bundled Nebius fixture illustrates the arithmetic trap using clearly labelled
sample inputs; it is not current market data. Verify actual growth, margins and
capex guidance in the latest filing before using the framework.

## The regime classifier

From yfinance-derived signals:
- **AI neocloud** — YoY revenue growth > 100% **and** capex/revenue > 30%.
- **Hypergrowth** — growth > 100% without heavy capex.
- **Early-stage** — revenue < ~$1M.
- **Steady** — everything else.

## What the engine outputs

1. **Dual-margin score** — Rule 40 computed twice, on EBITDA margin and on FCF
   margin. The delta is the broader **EBITDA-to-FCF gap**; it can reflect capex,
   working capital, cash taxes, interest, and other cash items.
2. **EBITDA-minus-capex proxy** — `EBITDA-based score − capex/revenue`. This is
   shown separately; capex is never subtracted from FCF twice.
3. **Dilution-adjusted score** — subtracts share-count growth from the FCF-based
   score so revenue "bought"
   with equity (common in hypergrowth AI names via SBC) isn't over-credited.
4. **Preferred score** — FCF-based for every regime; a neocloud with negative FCF
   margin cannot receive a green pass merely because growth is extreme.
5. **Stage/sector heuristic** — configurable project context, not a sourced market
   median or percentile.

## Analyst guidance

- Never quote the EBITDA-based neocloud score alone—pair it with FCF margin,
  capex intensity, the EBITDA-to-FCF gap, and the separately labelled proxy.
- Prefer a sourced peer distribution over any built-in pass/fail heuristic.
- Add trend context from aligned fiscal periods; one snapshot can mislead.
- For neoclouds, verify backlog/RPO in the latest filing as a forward signal—see
  [`ai-cloud.md`](ai-cloud.md).
