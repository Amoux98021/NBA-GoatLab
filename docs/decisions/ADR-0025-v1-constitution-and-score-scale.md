# ADR-0025: V1 Constitution authority and common dimension-score scale

## Context

The STEP-0012 candidate audit and STEP-0013 structural validation intentionally stopped before normative finalization. The attached `GOATLab_V1_Constitution_Methodology_Notes.docx` freezes the seven constitutional dimensions, their evidence ownership, and the rules governing missingness, era fairness, and active careers. Future agents need those binding rules in a stable repository artifact rather than relying on a binary attachment or narrative research notes.

## Decision

`docs/constitution/GOATLAB_V1_CONSTITUTION.md` is the machine-facing GOATLab V1 Constitution. It is a faithful extraction of the binding rules in the attached document and the STEP-0014 task; it excludes exploratory prose and player-ordering preferences. The original attachment remains the human-facing research history and has SHA-256 `5aed7e5803f4045598c5fce57c58e95ef59d63627be5fc5736c2b7602c16b79b`.

Every V1 dimension's final analytical value is mapped to 0–100 with a midrank empirical-CDF transform against the frozen 2,656-player `BROAD_HIGH_RECALL` population from STEP-0012. The scale is ordinal and outlier-resistant: 50 is approximately the reference median, 90/95/99 are approximately those observed percentiles, and tied values share a midrank. A score is never produced from missing evidence; coverage and confidence remain separate metadata and never multiply quality.

No official Overall score or dimension weights are selected in STEP-0014. Era Dominance remains a diagnostic, not an eighth additive dimension.

## Alternatives considered

- Raw min-max scaling was rejected because one historical extreme could compress the rest of the population.
- A normal-CDF mapping of z-scores was rejected because it imposes a distributional shape and gives extreme tails more apparent precision than the evidence supports.
- Per-era career scaling was rejected because player-season inputs are already era-normalized and a second era-specific scale would obscure a single common interpretation.
- Scaling only complete seven-dimension players was rejected because candidate-scoped Accolades and playoff evidence would make the reference population method-dependent.
- Treating confidence as a score penalty was rejected because incomplete historical observation is not low player quality.

## Consequences

The seven dimension scores are comparable as population-relative 0–100 descriptors, not interval claims that 100 is twice 50. Players outside the reference population can still receive scores and are never excluded from output. Legitimately unavailable dimensions remain NULL with explicit reasons. Future official Overall work must not redistribute an unavailable dimension's weight across the others.

## Status

Accepted for GOATLab V1 in STEP-0014.
