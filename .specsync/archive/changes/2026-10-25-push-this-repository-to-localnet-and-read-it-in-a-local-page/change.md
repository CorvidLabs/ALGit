---
id: push-this-repository-to-localnet-and-read-it-in-a-local-page
state: archived
type: feature
base_commit: 2aee85055fb43adf616f740eb998a6781e287dc7
---

# Push this repository to LocalNet and read it in a local page

## Intent

Push this repository to LocalNet and read it in a local page

## Affected Canonical Specs

- `algit`

## Acceptance Criteria

- I can push a git repository to Algorand LocalNet with one command.
- I can ask what the same push would cost on MainNet and see the ALGO before anything is spent.
- I can clone that repository back off the chain and git fsck accepts it.
- I can start a page on my own machine and read the commits, files, and diffs of what I pushed.
- A file that is too heavy for a note is pinned to the Pinata account in my PINATA_JWT, through the gateway in my PINATA_GATEWAY.
- The command has no CorvidLabs Pinata account of its own.
- The command and the page are one Python program.

## No-spec Rationale

Not applicable
