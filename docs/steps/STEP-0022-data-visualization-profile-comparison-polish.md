# STEP-0022 — Data visualization, player profile, and comparison polish

Date: 2026-09-22

Status: PASS
Scope: frontend presentation and data visualization only

## Objective

Make GOATLab's already-frozen uncertainty outputs easier to read on player profiles, comparisons,
and the methodology page without changing a score, probability, status, API request, or basketball
methodology. The visual system continues the STEP-0021 basketball-court, research-lab, and editorial
data-product identity.

## Visualization components

`frontend/src/components/data-visualization.tsx` adds reusable, server-rendered presentation
components:

- `RankDistributionGraphic` shows supplied 50%, 80%, 90%, and 95% rank intervals plus the median on
  a clearly labeled local axis derived from the displayed 95% extent. It explicitly states that the
  nested bands are intervals, not a fitted density.
- `ComparisonRankBands` places both players' supplied rank summaries on one combined local scale so
  overlap is directly comparable. It does not fit curves or sample distributions in the browser.
- `DimensionScaleGraphic` uses a fixed 0–100 scale. Point summaries receive a separate marker;
  available 90% intervals receive a probability-blue band; interval-only evidence receives no
  midpoint marker; unavailable evidence receives a textual state and no zero-valued track.
- `ComparisonDimensionGraphic` uses the same 0–100 scale for both players and preserves the same
  point, interval-only, and unavailable semantics without declaring a dimension winner.
- `MethodologyProcessGraphic` explains the frozen path from seven dimensions through aligned draws
  to rank/Top-N/pairwise outputs. Fixed weights remain exact text and gain proportional display bars.

The profile retains all prior textual band and probability values as visible, accessible backup.
Comparison retains the backend-supplied pairwise language and percentages. Dimension cards retain
status, supplied value/range, descriptions, confidence when supplied, and existing Peak-window
metadata.

## Truthful visual encoding

- lower numeric rank is explicitly identified as better;
- local rank axes show their numeric endpoints and are not compared across separate figures;
- comparison rank figures share one scale chosen from the two visible 95% extents;
- rank bands are nested interval bars, never bell curves or invented density;
- dimension positions are visual-only placement of already-supplied 0–100 values;
- collapsed factual intervals remain visible as a narrow blue interval mark without becoming an
  exact point claim;
- wider uncertainty changes range width, never the central quality estimate or color valence;
- amber marks point summaries/identity, probability blue marks intervals and probabilities, court
  tan supplies neutral track structure, and graphite supplies editorial structure.

## Motion and resource impact

The existing `MotionEnhancer` observes `data-interval-reveal` in addition to its prior targets and
performs one horizontal Web Animations reveal. The exact final geometry is already in server HTML.
Reduced-motion users, no-JavaScript users, and unsupported browsers receive the final static state.

- no dependency added;
- no endpoint or API contract changed;
- no client fetch added;
- no polling, keepalive, per-card request, scroll fetch, remote asset, or third-party service;
- server rendering, release checks, hourly revalidation, and existing backend request ownership are
  unchanged.

Expected additional backend requests: **zero**.

## Accessibility and responsive QA

- exact endpoints, percentages, scores, statuses, and unavailable copy remain visible text;
- interval figures and fixed-weight bars have meaningful accessible labels;
- comparison tables keep player names and numeric summaries adjacent to visual marks;
- no meaning depends on color, animation, or hover;
- focus behavior and semantic navigation remain unchanged;
- `prefers-reduced-motion` continues to disable substantive animation;
- profile, comparison, dimension, and methodology layouts were reviewed against the existing 375,
  768, and 1440 px breakpoint rules, with live local browser inspection at the tablet-width surface;
  narrow rules stack comparison lanes and preserve labeled endpoints without page overflow.

Local reference captures were used during QA for the profile interval panel, dimension cards,
comparison rank bands, shared dimension scales, and methodology weights/process flow. No screenshot
artifact was committed.

## Focused invariants

Tests now verify that:

- interval-only dimensions never render their diagnostic center or a point marker;
- unavailable dimensions never render a zero-valued scale;
- profile rank graphics preserve every supplied endpoint and disclose their local scale;
- comparison rank graphics use the identical combined scale for both players;
- pairwise probability values and ordering labels remain API-owned and exact;
- motion remains reduced-motion aware and neither motion nor visualization code adds `fetch`.

## Methodology preservation

No ranking methodology, formula, trained model, frozen release, player score, rank distribution,
probability, evidence status, API contract, database schema, backend behavior, leaderboard order, or
Top-100 membership semantic changed.
