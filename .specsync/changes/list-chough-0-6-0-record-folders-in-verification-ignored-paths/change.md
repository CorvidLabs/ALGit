---
id: list-chough-0-6-0-record-folders-in-verification-ignored-paths
state: approved
type: operations
base_commit: 992367ba7fbb724b89aa83122486cb094ea18d9b
---

# List Chough 0.6.0 record folders in verification_ignored_paths

## Intent

List Chough 0.6.0 record folders in verification_ignored_paths

## Affected Canonical Specs

- None

## Acceptance Criteria

- .specsync/sdd.json verification_ignored_paths lists .chough/sessions/, .chough/archive/ and .chough/bugs/; chough doctor reports no records_in_verification finding; specsync check passes

## No-spec Rationale

Policy-only edit to .specsync/sdd.json that adds Chough's three record folders to verification_ignored_paths; no module contract changes
