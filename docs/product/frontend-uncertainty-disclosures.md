# STEP-0016 frontend uncertainty disclosures

The product should say: **GOATLab models the GOAT debate with explicit, auditable assumptions.**
It must not say the model objectively solved the debate.

| UI element | Required copy/behavior |
|---|---|
| Display position `#N` | “Display rank is a navigation summary of the player's rank distribution. Nearby players may not be definitively ordered.” |
| Median rank | Label “Typical rank,” not “true rank.” |
| 90% rank band | “Under GOATLab's measurement uncertainty, this player's rank falls in this range in 90% of simulated outcomes.” Add “conditional on the frozen methodology” in detail view. |
| Top-N probability | Label probability of membership in the specified Top N, not an award or quality multiplier. |
| Interval-native status | Show range and source status. A diagnostic center may appear only if explicitly labeled beside that range. |
| Wider interval | “Wider uncertainty reflects less precise historical measurement, not lower player quality.” |
| Unavailable | “Insufficient evidence for a calibrated comparison.” Do not show `0` or a display position. |
| Pairwise 35–65% | “The available evidence does not support a meaningful ordering.” |

A leaderboard row needs name, navigation position, median rank, 80%/90% bands, Top-100
probability, Overall 90% range, and evidence status. A profile hero needs the same plus full
Top-1/5/10/25/50/100 probabilities and dimension summary. The seven-dimension panel must
honor official/provisional/interval/unavailable display rules; Accolades `NOT_QUERIED` is not
zero. Player comparison shows both ranges and the pairwise label, not just `P(A > B)`.

The public Top 100 is exactly 100 navigation slots, accompanied by a Top-100 boundary/bubble
disclosure. Bubble players outside the display list are not “worse” by definition. Keep the
archived V1 list clearly separated from this versioned product view.
