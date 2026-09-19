# ADR-0039 — Probabilistic-first ranking publication

Status: Accepted

Date: 2026-09-19

Related: ADR-0034 through ADR-0038, STEP-0015N, STEP-0015O, STEP-0015P

## Context

The seven-dimensional Overall V2 research architecture produces calibrated joint distributions.
STEP-0015N withheld an exact-point Overall promotion: 83 of the archived V1 Top 100 have an
interval-only Overall distribution, while only 17 have point-grade status. STEP-0015O found all
100 distribution-rankable and validated rank-band, Top-N, and pairwise probability calibration,
but central sort, median rank, expected rank, and expected wins all failed at least one frozen
exact-order gate. Historical measurement uncertainty remains a result, not a reason to retune
basketball formulas.

## Decision

1. Adopt `PROBABILISTIC_FIRST` publication governance under
   `goatlab-v1-ranking-policy-v2-probabilistic`. The canonical comparison object is a calibrated
   Overall distribution and the derived rank distribution, not one exact point or ordinal rank.
2. Permit a future **GOATLab Top 100 — Probabilistic Leaderboard** as a navigational list sorted
   by deterministic median-rank position with canonical-player-ID tie breaking. Display position
   is expressly not a validated exact scientific ordering or a promotion of an interval center.
   STEP-0016 must build and validate a production artifact; this ADR publishes no list.
3. A calibrated Overall distribution is the eligibility requirement. Official, provisional, and
   interval-native careers participate without status-based quality adjustment. Players lacking a
   required usable Overall distribution remain unranked with an insufficient-evidence explanation.
4. Every display entry exposes median rank, at least 80% and 90% rank bands, Top-100 membership
   probability, Overall range, evidence status, cutoff, and version. Player details also expose
   50%/95% bands, Top-10/25/50/100 probabilities, and pairwise comparison access. If a center is
   shown, label it a diagnostic summary and display its interval alongside it.
5. Top-100 membership language uses probability thresholds of at least 90% robust, 65%–90%
   likely, 35%–65% bubble, 10%–35% likely outside, and below 10% robustly outside. Pairwise
   ordering uses at least 90% strong, 65%–90% lean, 35%–65% indeterminate, and symmetric reverse
   labels. These labels never alter quality or eligibility.
6. `goatlab-v1-overall-v2-tiered` is the frozen **research probabilistic substrate**, not a
   promoted exact-point Overall methodology. The STEP-0015N
   `DO_NOT_PROMOTE_OVERALL_V2` conclusion and every calibration gate remain intact. Overall V1
   and its archived Top 100 remain immutable historical artifacts.
7. All probabilities are conditional on the frozen measurement architecture; shared cross-player
   calibration-model uncertainty is not fully modeled. Active careers use
   `TO_DATE_NO_PROJECTION` through 2025-26.

## Consequences

- STEP-0015 forensic research closes. STEP-0016 productization may materialize the navigational
  list and APIs under this policy without changing basketball formulas or silently upgrading the
  Overall point methodology.
- A `#N` display position needs nearby rank-band/probability context and an explanation that
  adjacent players may be statistically indistinguishable.
- Wider uncertainty is never lower player quality. Missing historical evidence is never zero.
- Reopening STEP-0015 methodologies requires a concrete defect or material new data, not an
  unconventional-looking leaderboard or a wish for exact ranks.
