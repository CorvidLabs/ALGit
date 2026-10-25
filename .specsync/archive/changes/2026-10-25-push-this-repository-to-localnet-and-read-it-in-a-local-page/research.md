---
change: push-this-repository-to-localnet-and-read-it-in-a-local-page
artifact: research
---

# Research

`docs/onchain-git-remote.md` records the LocalNet measurement from 24 October 2026. Public notes begin with `ALGT`. A 4,096-byte note cost 1,308 microALGO, a 1,024-byte note cost 1,000, and a 1,025-byte note cost 1,001. `py-algorand-sdk` 2.12.0 builds a note longer than 1,024 bytes. 2.11.1 does not.

This repository is one commit and about twenty git objects. That is small enough to push and read back on the sandbox in one sitting. `site` is the history that was too expensive to treat as a product. It is not the history this change pushes.

A blob over 256 KiB is the stand-in for "too heavy for a note." This repository has none. The pin path is still part of the command, and it uses only the caller's Pinata account.
