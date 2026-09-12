# Peak V1 forensic audit

Methodology: `goatlab-v1-peak-forensic-audit-v1`  
Frozen Peak source: `goatlab-v1-dimension-scores-v1`  
Verdict: **REQUIRES_REVISION**

## Exact V1 definition

Every input is a qualified Regular Season era percentile on `[0,1]`.

1. `Scoring = 65% PPG + 35% TS`; PPG is required and observed weights renormalize when TS is unavailable.
2. `Offense = 65% stronger(Scoring, APG) + 35% secondary`; a lone available axis receives 100% of the value.
3. `Actions = 50% RPG + 25% SPG + 25% BPG`; observed weights renormalize.
4. `Defense = 65% TeamSuppression + 35% Actions`; TeamSuppression is required and becomes 100% when Actions is unavailable.
5. `SeasonQuality = 65% stronger(Offense, Defense) + 35% secondary`; a lone axis receives 100%.
6. `RawPeak = 70% best complete contiguous three-season mean + 30% best single-season apex`.
7. Raw Peak receives the frozen broad-reference-population midrank ECDF transform to `[0,100]`.

The seven primitive local weights are PPG .65, TS .35, APG .35, TeamSuppression .65, RPG .50, SPG .25, and BPG .25. These are nested rather than directly additive, so the realized global weights vary with which axis is stronger and which values exist.

## Reconstruction

All 5,103 player rows reproduce exactly. Raw season quality, season percentile, three-year component, apex, raw Peak, and final ECDF score have maximum absolute difference `0.0`. Frozen non-Peak dimensions and Overall V1 are unchanged.

## Effective influence

| Primitive | Mean realized weight | Covariance/Shapley variance share | Leave-one-out MAE (points) |
|---|---:|---:|---:|
| PPG | 26.63% | 32.26% | 9.82 |
| APG | 19.10% | 24.67% | 6.18 |
| Team suppression | 34.34% | 30.17% | 14.28 |
| RPG | 6.73% | 4.83% | 1.83 |
| TS | 7.02% | 4.26% | 2.56 |
| SPG | 3.09% | 2.69% | 1.31 |
| BPG | 3.10% | 1.11% | 0.87 |

Team suppression has the largest mean realized weight and leave-one-out effect. The formula is not a flat balanced sum: its stronger-axis rule allows team suppression to realize 42.25% of season quality when Defense is the stronger axis, versus 22.75% when Offense is stronger.

## Team-context inheritance

Team suppression has zero within-team-season variance and 97.65% between-team eta-squared in the player-level audit representation. It correlates `0.5533` with final season quality and `0.4396` with career raw Peak. Of 133,105 teammate pairs, 104,097 receive identical team credit. Final season quality itself has between-team eta-squared `0.3097`.

That context can be useful supporting evidence, but its realized influence is too large to represent individual overall Peak faithfully.

## Missingness and evidence regimes

Missing evidence is never zero. It is explicitly removed and the observed weights renormalize. That protects null semantics but does not preserve one common construct.

On 16,308 rich-evidence seasons:

| Mask | MAE | RMSE | Spearman | Shift >5 points |
|---|---:|---:|---:|---:|
| Current/full | 0.00 | 0.00 | 1.0000 | 0.00% |
| No STL/BLK | 2.10 | 2.87 | 0.9951 | 8.24% |
| No TS | 3.29 | 4.45 | 0.9882 | 22.87% |
| No team context | 13.53 | 16.92 | 0.8290 | 76.32% |

No-STL/BLK masking has signed role effects: bigs `+1.66`, guards `-1.64`, forwards `+0.89`, and wings `-0.99` points. Removing team context shifts guards upward by `+6.11` points on average and bigs downward by `-6.29`, demonstrating archetype-sensitive weighting.

## Three-year and apex layers

The window layer is correct. Missing or nonqualified seasons break contiguity, equal windows select the earlier start deterministically, and `100/100/missing` cannot produce a three-year Peak. The 2,456 valid V1 Peaks have three-year/apex Spearman `0.9512`. V1 versus 60/40 and 80/20 has Spearman `0.9996`; V1 versus the three-year component alone is `0.9968`. The apex adds meaningful but secondary differentiation. It uses exactly the same season-quality construct as the three-year component.

Games determine qualification (`max(5, ceil(20% of team opportunity))`) and confidence, not performance quality. Minutes do not enter the formula. Career length outside the selected window contributes no Peak value.

## Specialist and diagnostic behavior

Synthetic balanced two-way evidence at the 90th percentile produces season quality `0.9000`. An extreme defensive specialist produces `0.7644`, an extreme offensive specialist `0.7485`, an interior-anchor profile `0.7652`, and a primary-creator profile `0.7648`. Dominant specialists can therefore reach elite values, which is constitutionally permissible. The concern is that the defensive specialist result depends heavily on a shared team outcome, not merely individual dominance.

Rudy Gobert's V1 Peak is `97.3931`, from 2016-17 through 2018-19. His defense axis is stronger than offense, causing team suppression to carry 42.25% of each window season. His team-suppression percentiles are `1.0000`, `0.9828`, and `0.8966`.

Stephen Curry's V1 Peak is `95.5601`, from 2013-14 through 2015-16. His offense axis is stronger, so team suppression carries 22.75%; elite offense is partly offset by team-suppression percentiles `0.6897`, `0.5172`, and `0.3793`.

Shaquille O'Neal's V1 Peak is `92.7495`, from 1999-00 through 2001-02. His offense axis is also stronger, but the middle season's team-suppression percentile is `0.2143`, lowering that season's quality percentile to `0.8632` and the three-year mean.

Removing only team suppression changes the raw ordering to Curry (`0.9994`), Shaq (`0.9842`), Gobert (`0.8169`). Removing BPG alone flips Gobert and Curry. This identifies the mechanism; it is not a request to force a preferred player order.

## Scale and external validation

ECDF is monotone and does not create the Gobert/Curry/Shaq ordering. It does compress the elite tail: raw P95 is `0.97025`, P99 is `0.99448`, and near P95 approximately `0.00465` raw Peak corresponds to one ECDF point. Peak standard deviation is `2.70` among the official Overall Top 100 and `0.81` among the Top 25.

Awards are validation only. MVP seasons average the `95.59` season-quality percentile; 87.32% are at or above P90. All-NBA First seasons average `92.40`; 74.00% are at or above P90. Disagreement remains visible and no recognition enters Peak.

Peak correlations are high with Offense (`0.8078` Spearman), Defense (`0.6160`), and Longevity (`0.8957`). The especially high Longevity overlap reflects the shared season-quality base even though Peak itself uses only one- and three-season windows.

## Research candidates and decision

Four non-production candidates were compared. The strongest constitutional research direction is `C_MULTI_PATH_ROLE_ACTIONS`: require season Offense and role-aware individual action evidence, combine the stronger axis at 65% and secondary at 35%, then preserve the 70/30 Peak layer. It removes team context and has Spearman `0.8787` with V1.

It is not promoted. Only 1,761 reference players receive a score; actions remain incomplete proxies for defense; historical role coverage is incomplete; and some careers acquire implausible later windows because earlier evidence is unavailable. Its research-only Overall counterfactual covers 1,391 common eligible players, has Spearman `0.9918` with V1, and Top-10/25/50/100 overlap `0.90/0.96/0.86/0.94`.

The correct next move is a dedicated season-value architecture/promotion audit with explicit evidence-regime calibration. Frozen V1 remains reproducible but is not constitutionally adequate as the final Peak methodology.
