# Data dictionary

This document indexes project-owned data concepts. Canonical Silver field definitions are added with schema implementation in STEP-0003. The source-specific physical dictionary remains in the `nbadb` source audit and mapping documents.

## Missingness vocabulary

- **Observed zero:** the metric was applicable and recorded with value zero.
- **Missing value:** the metric should be present under known coverage but the value is absent.
- **Historically unavailable:** the metric was not officially recorded or did not exist for the observation's era.
- **Source unavailable:** the provider or acquired snapshot lacks usable coverage despite conceptual applicability.

None of these states may be silently converted into another.
