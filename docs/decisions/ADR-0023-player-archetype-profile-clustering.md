# ADR-0023: Profile-shape clustering for player archetypes

## Context

Clustering magnitude-preserving career features can merely separate stronger and weaker careers. GOATLab needs descriptive player-performance profiles, not hidden quality tiers. Cluster labels are also algorithmically arbitrary.

## Decision

Evaluate both column-standardized magnitude-preserving profiles and profiles that are additionally row-centered and row-RMS-scaled. Select archetypes only from the shape representation. Compare K-means for k=2 through 12, diagonal and spherical Gaussian mixtures, and a bounded deterministic average-linkage audit. Report silhouette, Calinski-Harabasz, Davies-Bouldin, AIC/BIC, cluster sizes, uncertainty, seed/bootstrap ARI and AMI, method agreement, era association, and active-career sensitivity.

Cluster labels are canonicalized by a hash of rounded centroids, never by quality or a named player. Descriptions use relative feature emphasis. Player examples are selected only after fitting by centroid proximity or mixture uncertainty. Position is withheld until full-corpus canonical position coverage is validated.

## Alternatives considered

- Magnitude-only clustering was rejected as the primary archetype definition because it can produce quality tiers.
- Naming clusters after famous players was rejected because examples would become implicit training targets.
- Forcing a predetermined cluster count was rejected; model-selection diagnostics determine the supported granularity.
- Full O(n²) hierarchical clustering was rejected for the main population; a deterministic 300-player audit with transparent full assignment is used.

## Consequences

The V1 archetypes are coarse diagnostics and are not player rankings. Weak agreement between model families limits taxonomic claims even when K-means itself is stable. A future product may show profiles only with these caveats.

## Status

Accepted for STEP-0013 diagnostics; archetype labels are non-final.
