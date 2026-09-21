# Publication-rights gate

Status: `PUBLICATION_RIGHTS_REVIEW_REQUIRED`.

This repository contains derived basketball analytics and public identity metadata, not raw source
dumps. That technical minimization does not itself resolve contractual, database-right, trademark,
or publication questions. STEP-0020 does not provide legal advice and does not approve publication.

## Required decision record

An authorized owner must record:

- datasets/source families reviewed and intended public fields;
- applicable license/terms analysis and attribution requirements;
- whether derived rankings, player identity metadata, and display names may be published;
- restrictions on commercial use, caching, redistribution, or player imagery;
- approver, decision date, scope, and any expiry/re-review date.

Until then:

- production-like environments are previews only;
- frontend metadata, headers, and robots rules block indexing;
- no public launch announcement or custom public domain promotion occurs;
- player photography/source payloads remain excluded;
- `GOATLAB_PUBLICATION_RIGHTS_APPROVED` stays `false`.

After approval, changing that environment flag only changes indexing metadata. It must not alter
the release, scores, probabilities, methodology, or ranking status. A denial requires keeping the
service private or revising product scope in a separately authorized step.

STEP-0020B did not deploy a public or private live environment and did not change this gate. Even
after technical deployment is completed, the service remains preview/private and non-indexable
until the independent decision record above exists.
