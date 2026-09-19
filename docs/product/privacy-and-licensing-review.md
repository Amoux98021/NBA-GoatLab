# STEP-0016 privacy and source-rights review

Reviewed: 2026-09-19. This is an engineering inventory, **not legal clearance**.

The generated product artifacts contain release-scoped player names/IDs, career bounds,
derived GOATLab dimension/Overall/rank analytics, evidence/status metadata, reason codes,
and empirical GOATLab draws. They do **not** contain raw player-game rows, NBA endpoint payloads,
source request headers, photos, video, addresses, credentials, or private user information.
The serving schema intentionally omits NBA trademarks/logos and raw vendor columns. It includes
professional basketball player identity and season metadata already in the canonical project
corpus; no user-account personal data is processed.

The source corpus includes NBA Statistics. [NBA.com Terms of Use](https://www.nba.com/termsofuse)
currently specify attribution and restrictions on use/display/publication of NBA Statistics,
including private non-commercial/news contexts and limits on commercial products and
comprehensive regularly updated statistics databases. A derived analytics artifact is not by
itself proof that a public or commercial GOATLab launch is authorized. Before any external
deployment, a responsible owner must review the intended product, attribution, monetization,
source agreements, trademark treatment, and whether permission or a separate license is needed.

Accordingly STEP-0016 builds **local, ignored, non-deployed artifacts** and read-only service
primitives only. It does not publish files to a CDN, activate Neon, expose an API to the public,
or claim legal permission. The product deployment checklist must include a source-rights decision
separate from methodological validation. If rights are insufficient, keep the release internal or
obtain a suitable license before external distribution.
