# STEP-0015P — Probabilistic Ranking Governance Freeze & STEP-0015 Closure

Date: 2026-09-19

Step status: `PASS`

Governance verdict: `FREEZE_PROBABILISTIC_FIRST_POLICY`

Ranking policy: `goatlab-v1-ranking-policy-v2-probabilistic`

Recommendation: `CLOSE_STEP_0015_AND_BEGIN_STEP_0016`

## Scope and immutable inputs

This is a governance and product-contract change. No basketball formula, source record, model,
calibration gate, dimension artifact, V1 ranking, or research rank distribution is changed. The
worktree was clean at STEP-0015O commit `3cd3d1c16e207c24ad88709a6b4edbe491bf6b97`.

The prior audit fingerprints remain:

- STEP-0015M Defense V2: `a2056a6d793b2f82066c07bc4924787d3e95f8485ef37ff15911bfb7a321deb7`;
- STEP-0015N Overall joint: `b6248062490ca6b2d63e616af5ac759a59abc9ea3e9dc15dd4f2bd264741bb95`;
- STEP-0015O rank audit: `544843af8d316c6b5d54786b29562451ce01e3f6b5c35a0fe936e27fa2290a15`;
- archived V1 Overall: `02bacaaacbff1a038ca0b5a82c6d3b51e34e192426e51ad8f0b72cd89bda97aa`.

No STEP-0015O validation or basketball computation was rerun for policy selection. The audit
remains `VALID_PROBABILISTIC_RANKING_ONLY`: all four exact-summary candidates failed at least
one frozen gate, while conditional rank bands and Top-N/pairwise probabilities calibrated.

## Governance decision

Accept `PROBABILISTIC_FIRST`. The canonical object is the versioned calibrated Overall
distribution and derived rank distribution. The decision changes a *product requirement*, not the
measured player qualities: a future Top 100 can be a median-rank-sorted navigation list, with
status, ranges, bands, and probabilities clearly presented. A `#N` display slot is not a claim
that the player is definitively better than the next slot. The policy is specified in
[ADR-0039](../decisions/ADR-0039-probabilistic-first-ranking-publication.md) and the versioned
registry.

STEP-0015P does **not** promote `goatlab-v1-overall-v2-tiered` as an exact-point methodology,
overrule STEP-0015N's failed point gate, or publish an official V2 Top 100. The joint architecture
remains the frozen research probabilistic substrate for the next product phase. Archived Overall
V1 and its Top 100 remain separate, reproducible historical outputs.

## Publication and status contract

Distribution-rankable means a calibrated Overall distribution with no completely unavailable
required evidence. `OFFICIAL`, `PROVISIONAL`, and `INTERVAL_NATIVE` are evidence statuses, never
quality multipliers. `UNAVAILABLE` is unranked with exact blocking reasons; neither missingness
nor uncertainty becomes zero performance.

Future list entries must show at least median rank, 80%/90% rank bands, Top-100 probability,
Overall range, status, and a navigation-only display-position explanation. Profiles also support
50%/95% bands, Top-10/25/50/100 probabilities, dimension statuses, and pairwise comparisons. A
diagnostic Overall center may appear only explicitly labeled and adjacent to its interval.

Membership: at least 90% robust Top 100, 65%–90% likely, 35%–65% bubble, 10%–35% likely
outside, below 10% robustly outside. Pairwise: at least 90% strong evidence, 65%–90% lean,
35%–65% indeterminate, and symmetric reverse labels. These words do not reorder players or alter
scores. All probabilities are conditional on the frozen measurement architecture; shared global
calibration-model uncertainty is not fully modeled. Active careers remain
`TO_DATE_NO_PROJECTION` through 2025-26.

## Forensic branch closure

The full [retrospective](../data/step-0015-final-retrospective.md) records:

- Defense V1 team inheritance; tiered Defense V2 resolves dominance but observed Presence remains
  observational and effectively influential.
- Peak V1 contaminated SeasonQuality; promoted Peak V2 retains the 70/30 height architecture with
  uncertainty-aware season evidence.
- Longevity P80/P90 and 35/40/25 remain conceptually fixed; weak historical evidence is
  interval-native instead of forced into an exact point.
- Factual early data recovery changed the coverage picture; missing creation/defensive statistics
  are not fabricated.
- Tiered PlayerSeasonValue, paired Peak/Longevity, Defense dependence, and Overall joint
  distributions improve historical comparability without granting exact cross-era certainty.
- Exact ordinal rank publication failed; calibrated probabilistic comparison is the durable
  research result.

The unequal historical measurement environment cannot be eliminated. Wider uncertainty is not
lower player quality. Formula changes motivated solely by unexpected famous-player placements are
not authorized. Reopening requires a concrete defect or material new factual evidence.

## Deliverables

- Constitution clarification and [ADR-0039](../decisions/ADR-0039-probabilistic-first-ranking-publication.md).
- Frozen [ranking-policy registry](../data/goatlab-v1-ranking-policy-v2-probabilistic.yaml).
- Typed `PlayerLeaderboardRecord`, `UnrankedPlayerRecord`, and `PairwiseComparison` validators in
  `src/goatlab/rankings/publication_policy.py`.
- [Product/API handoff](../data/probabilistic-ranking-product-contract.md) and final retrospective.
- Governance manifest with upstream SHA-256/fingerprint checks and a deterministic policy
  fingerprint. No ranking artifact or player row is committed.

## Verification

- Frozen upstream methodology registries, V1 summary, Peak/Defense/Longevity summaries,
  STEP-0015N and STEP-0015O summaries are hash-checked without mutation.
- Boundary tests enforce probability levels, symmetric pairwise labels, tier status mapping,
  missing-player exclusion, interval/band nesting, center/display labels, version completeness,
  cutoff, and no uncertainty penalty.
- The full repository test, lint, and applicable type/data-validation checks are recorded in the
  final handoff.

Governance fingerprint: `9511a3c85fe429da80cdf485715d8168c75046373ea6504ece50478943ca802d`.

## Next phase

STEP-0015 is **closed**. Begin a new numbered STEP-0016 — Probabilistic Leaderboard Data Product.
Materialize versioned distribution-backed leaderboard, player-profile, and pairwise datasets;
specify database and FastAPI schemas; define Next.js content/UI requirements; and validate
publication provenance and human disclosures. Do not change basketball methodology in that phase.
