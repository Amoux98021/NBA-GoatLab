# Disaster recovery

## Recovery objectives and sources of truth

No formal RTO/RPO is promised yet. The service is read-only and reproducible: Git contains code,
migrations, and policy; controlled object storage contains the fingerprinted release bundle; the
database contains an immutable derived copy. The object bundle and approved Git commit are the
recovery sources, not an ad hoc database export.

## Database loss

1. Create a fresh PostgreSQL database/branch.
2. Verify the approved migration checksum.
3. Apply migrations with the controlled loader credential.
4. Materialize and verify the frozen release bundle.
5. Transactionally load it; reconcile all table counts/fingerprints.
6. Create/grant the SELECT-only runtime role and rotate URLs.
7. Run smoke tests before restoring traffic.

## Artifact loss or corruption

Remove the affected instance. Fetch the same hash-pinned bundle to a fresh ephemeral directory.
The API must not start if bundle SHA, release fingerprint, per-file hashes, or draw hash differ.
Never regenerate a replacement under the same release ID from changed inputs.

## Bad application deployment

Rollback the frontend/API to the last immutable deployment. Database content is unchanged. If a new
future release was selected, roll back release ID, API artifact, DB content availability, and
frontend configuration together; mixed-release serving is forbidden.

## Credential compromise

Revoke/rotate the affected provider secret, DB role, and bundle token. Runtime DB credentials are
read-only, so a compromise must still be investigated but cannot legitimately rewrite releases.
Audit logs and verify immutable table triggers/content before returning traffic.

Recovery exercises should occur before launch and after any topology change. Results belong in an
append-only deployment record, not in the frozen ranking release.
