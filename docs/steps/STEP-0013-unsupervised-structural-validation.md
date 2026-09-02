# STEP-0013 — Unsupervised structural validation, latent factors, and player archetypes

## 1. Objective

Use unsupervised methods to test the latent structure, redundancy, incremental uniqueness, and profile archetypes in STEP-0012 without producing an overall score, player ranking, or final dimension formula.

## 2. Motivation

Thirty-two candidate definitions survived STEP-0012, but high correlations and shared lineage showed that treating them—or all eight proposed dimensions—as independent votes would be unsafe. Structural validation is required before final methodology work.

## 3. Inputs

- GOATLAB-HIST-V1: `283c528f487024e5292eaac06018364ee863ba623244e5dca4a0f958f100c70c`
- Era normalization: `a488aaa0c48a464c95afe276a3d2a142eabcc4a69edda7dcc77ebc53644f5852`
- Career primitives: `5ca40fca8163d0ca89b4ccdd6ca2cca0483e4e94a23e20c7b2140f4d7b08e37b`
- Awards: `666dbbdffd457847342754e116a857db7821e514e304ee23fe118f6d4a5bb258`
- Team success: `707be9dccdbccd70ba88d0f57d66af990f0cc5fd07127221a7aa0b7d2f17c333`
- All-Star/stat leaders: `e0a3bab4ef5957ab4e0acc1a669f82f508217d139b30599df970248f8c1d1880`
- Dimension candidates: `e5cd648afbc36306251ec1229b4c9f2beba830ca0ce93056c8e783e596bfc11f`

No network, external ranking, target label, or new basketball source was used.

## 4. Work performed

- Built and audited dimension-candidate, cross-era primitive, modern-enriched, magnitude-profile, and shape-profile matrices across four populations.
- Enforced complete intersections with explicit exclusions and no zero/mean imputation.
- Compared standard and robust scaling.
- Ran deterministic SVD PCA, parallel analysis, reconstruction diagnostics, component matching/sign alignment, bootstrap stability, population sensitivity, and active-career sensitivity.
- Ran iterated principal-axis factor analysis separately for two through ten factors with Varimax, held-out reconstruction, and bootstrap loading stability.
- Quantified candidate cross-family correlation, multiple R², residual variance, component/factor loading, and incremental uniqueness.
- Tested Era Dominance independence, Accolades A/B/C, Peak B/D/E, and all-era versus modern Defense.
- Evaluated K-means k=2–12, diagonal/spherical GMMs, and deterministic average-linkage clustering with ARI/AMI stability and era/active bias audits.
- Produced post-fit, centroid-selected player examples and a non-final candidate shortlist.
- Ran the complete build twice and required an exact output fingerprint.

## 5. Files created or changed

- `src/goatlab/models/structural_validation.py`
- `pipelines/models/build_structural_validation_v1.py`
- `tests/test_structural_validation.py`
- `tests/test_structural_validation_artifacts.py`
- `pyproject.toml` (NumPy is now an explicit direct dependency)
- ADR-0022 through ADR-0024
- `docs/data/ML_STRUCTURAL_VALIDATION_V1.md`
- Nine committed structural reports/registries plus `structural-validation-summary.json`
- `docs/PROJECT_LOG.md`, `docs/METHODOLOGY.md`, `docs/DATA_DICTIONARY.md`, and `docs/EXPERIMENTS.md`
- Ignored Gold/diagnostic figures under `data/gold/ml_structure/`

## 6. Data observations

- The 32-candidate matrix retains 1,391 of 2,656 broad players and strongly selects later cohorts; no pre-1960 debut is present in the complete intersection.
- Four PCA components exceed the fixed-seed parallel-analysis threshold and explain 83.17% cumulatively.
- PCA loadings are highly stable; four-component mean bootstrap loading correlations are 0.989–0.994.
- The selected seven-factor Varimax solution has stable loadings and separates empirical families more clearly than unrotated PCA.
- Era candidates are 93.4%–99.2% predictable from other candidate families on the complete matrix.
- Shape K-means supports two coarse profiles with weak era association, but GMM and hierarchical agreement is limited.
- Eighteen candidates remain on the experimental shortlist; none is final.

## 7. Decisions made

- Preserve multiple coverage-qualified matrices rather than impute a universal matrix (ADR-0022).
- Use row-centered profile clustering for archetypes and treat cross-model disagreement as a limit (ADR-0023).
- Recommend Era Dominance as a diagnostic lens rather than an additive eighth dimension (ADR-0024).
- Recommend seven conceptual families for STEP-0014 consideration while retaining all upstream evidence.
- Keep modern advanced Defense separate from the all-era structural question.

## 8. Validation/tests executed

- Offline unit tests for complete-case handling, scaling, PCA, parallel analysis, sign/component alignment, factor analysis, candidate uniqueness, profile transformation, K-means, GMM covariance, clustering metrics, ARI/AMI, and hierarchical behavior.
- Committed artifact tests for fingerprints, model contracts, bias controls, pruning statuses, and non-final shortlist semantics.
- Full `pytest`, Ruff, strict Mypy, and artifact validation.
- Two full offline builds; the second required fingerprint `0f06e17c382de61a260dbd9eabb872a0613bf2c2146468c2a81bd454c4951093`.

## 9. Results

**PASS.** The structural diagnostics are reproducible, coverage-aware, and free of target rankings. Four stable PCA components and seven stable rotated factors describe overlapping rather than eight independent additive signals. The profile-clustering result is usable only as a coarse two-archetype diagnostic. Candidate pruning reduces 38 definitions to an 18-candidate non-final shortlist.

## 10. Known limitations

- Complete candidate analysis is severely later-era selected.
- The factor method is principal-axis rather than maximum-likelihood FA.
- Cross-model clustering agreement is weak to moderate despite strong K-means stability.
- Early Defense and candidate-scoped award evidence remain structurally incomplete.
- Hierarchical clustering uses a deterministic 300-player audit subset.
- Position coverage was not qualified for archetype modeling.

## 11. Next step

Recommended STEP-0014: finalize a small set of dimension definitions through coverage-stratified sensitivity and explicit ownership choices, using the 18-candidate shortlist as input. It should preserve Era Dominance as a diagnostic, maintain all-era/modern separation, and still avoid an overall GOAT ranking unless separately authorized.
