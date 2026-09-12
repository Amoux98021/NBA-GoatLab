# Defense V1 Forensic Audit

Methodology: `goatlab-v1-defense-forensic-audit-v1`  
Frozen comparison: `goatlab-v1-dimension-scores-v1` / `goatlab-v1-overall-v1`  
Output fingerprint: `07397e117ed79aff52a7a1bb58c868f5100bb0560a826e736f35cf0579d80324`  
Constitutional verdict: **REQUIRES_REVISION**  
Audit result: **PASS**

## Baseline reconstruction

The audit independently recreated the season inputs, career means, and frozen 2,656-player midrank ECDF. All 5,103 player outputs match exactly: zero mismatches and maximum absolute score difference 0.0. No frozen Dimension or Overall artifact was rewritten.

The exact V1 season formula is `0.65 × team suppression + 0.35 × action context`. The action context is `0.50 × RPG percentile + 0.25 × SPG percentile + 0.25 × BPG percentile`, with observed-evidence renormalization. Although earlier documentation used the generic phrase “rebound context,” the implementation uses total rebounds, not defensive rebounds. Missing steals/blocks remain missing rather than zero.

## Why the three trigger scores occur

- Stephen Curry: career team-suppression input 0.441810 and action input 0.685720 produce raw `0.527179`, which maps to 61.6428 on the V1 ECDF. The action channel, especially guard-relative disruption/rebounding evidence, is stronger than his team-context average.
- Kobe Bryant: team suppression 0.402871 and action context 0.755687 produce raw `0.526357`, mapping to 61.5298. Strong recorded action evidence is substantially offset by the majority-weight team input.
- Rudy Gobert: team suppression 0.807692 and action context 0.859929 produce raw `0.825975`, mapping to 98.9827. Both channels are elite; no award evidence enters the result.

These explanations are mechanical and were not used to choose a replacement.

## Position and role audit

Reliable source position metadata maps 3,612 players; 69.9% of the master population has a recognized broad role. V1 mean/median Defense by broad role is: big 50.51/50.49, forward 46.64/45.21, wing 46.77/47.83, guard 41.07/36.96. The share at or above Defense 90 is 13.85% for bigs, 12.85% for forwards, 6.79% for wings, and 9.39% for guards.

That raw disparity is evidence of structural role sensitivity, not proof of mismeasurement by itself. On the 1,587-player position-qualified modern overlap, residual effects after regressing official advanced defensive-rating evidence on V1 are small (standardized means from -0.059 to +0.043). The audit therefore does **not** claim a demonstrated residual guard penalty against that noisy validator. It does find that total rebounding and blocks structurally provide more observable action evidence to frontcourt roles, while historical perimeter containment is unobserved.

## Team attribution and teammate collision

The V1 suppression input is exactly identical for teammates in a team-season. Its within-team variance is 0 and ICC is 1.0. Among single-team player-seasons, 89.92% of final raw-composite variance is between team-season groups. At career level, raw Defense correlates 0.8661 with team suppression and 0.4450 with action context.

There are 9,171 player pairs sharing at least three team-seasons with usable action evidence; 4,257 pairs differ by at least 0.25 in mean action evidence while receiving exactly the same suppression credit in the shared seasons. This is the decisive constitutional attribution problem.

## Defensive Presence Impact feasibility

The experimental model reconstructs team-game opponent scoring from the frozen official player-game facts, controls for opponent team offensive average and season environment, then contrasts positive scoring-prevention residuals in games with and without the player for each team-season. Trades remain separate.

It requires 10 games with and five without. Effective sample size is `n_with × n_without / (n_with + n_without)` and the raw contrast is shrunk by `n_eff / (n_eff + 20)`. The model produces 17,089 eligible player-seasons. Across 28,817 player-team-season records, 2,357 are STRONG, 12,249 MODERATE, 4,344 LIMITED, and 9,867 INSUFFICIENT_SAMPLE. Insufficient evidence is NULL, never zero.

This is a WOWY-style game-presence estimate, not RAPM. The frozen player-game contract does not expose venue assignment, so home/away adjustment is unavailable in this implementation. Game participation also cannot identify possession-level teammate effects. These limitations reduce confidence and block causal claims.

The 17,089 eligible estimates cover 71.63% of V1-qualified player-seasons after matching the V1 comparison rows. DREB evidence is observed for 16,301 qualified player-seasons.

## Candidate comparison

- V1: 65% team / 35% total-rebound-steal-block action.
- A: 45% team / 55% role-aware action.
- B: 30% team / 30% role-aware action / 40% stabilized presence.
- C: 35% / 35% / 30%, coverage-adaptive.
- D: 40% / 35% / 25%, with no modern correction.

Candidate B is the V2 counterfactual because it most directly resolves the team-attribution violation while keeping team context, role-aware actions, and conservative presence evidence distinct. When DREB is reliably available it replaces total rebounds; otherwise the fallback is explicitly labeled `TOTAL_REBOUND_PROXY`. Role adjustment blends 65% league-wide and 35% broad-role rank, so it moderates evidence bias without forcing equal position ceilings.

Candidate B is materially different from V1: Defense-score Spearman is 0.7876 and Defense Top-25/50/100 overlap is 40%/52%/52%. That is evidence against silent promotion, not a reason to tune the candidate toward V1.

Official advanced defensive rating is a weak validator for every candidate: V1 Spearman 0.2813; B 0.2501. That small decrease does not favor B, and modern defensive rating is itself team-dependent. Award validation, used only after construction, is stronger for B: 51.34% of All-Defense players and 74.07% of DPOY players are at or above Defense 90, versus 41.71% and 59.26% under V1.

## Score-scale interaction

V1 Defense has standard deviation 31.87 across scored players, the largest of the seven dimensions. In the official Top 100 its standard deviation is 9.50, versus 2.41 Longevity, 2.70 Peak, 3.69 Accolades, 5.12 Playoffs, 6.05 Offense, and 7.64 Winning. At 14% Overall weight, Defense contributes a 1.33-point standard deviation within the Top 100. ECDF scaling therefore makes Defense unusually differentiating among elite profiles even though the scale remains 0–100.

## V2 counterfactual only

Using frozen Overall weights, the Defense-V2 counterfactual has Spearman 0.9958 with published Overall V1. Top-10/25/50/100 overlaps are 70%/88%/94%/95%. These changes are disclosed, not promoted. The published ranking and seven-dimension methodology remain unchanged.

Mean Overall rank movement is +3.71 for guards and +2.15 for wings, versus -3.83 for bigs and -3.39 for forwards (positive means a better counterfactual rank). STEP-0013 profile clusters shift in opposite directions (+7.85 and -8.38 mean ranks), confirming archetype sensitivity. Debut-decade mean shifts range from -4.33 to +8.13. No quota or correction is applied.

## Limitations

- Position metadata covers 69.9% and source labels are coarse.
- Perimeter containment, screen navigation, rim deterrence, and rotations are not directly observed historically.
- Presence estimates are unavailable when a player rarely missed games and remain vulnerable to teammate/game-selection confounding.
- Home/away and full lineup adjustment are not in the portable estimate.
- Modern defensive rating and awards are imperfect validators, not ground truth.
- Candidate weights are constitutional/modeling judgments and require a separate promotion audit.

The second offline run reproduced the same six Parquet hashes and report hashes with zero network requests. Total audit Gold size is 2,969,085 bytes; the certification run completed in 12.92 seconds on the recorded host.
