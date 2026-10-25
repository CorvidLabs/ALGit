---
change: push-this-repository-to-localnet-and-read-it-in-a-local-page
artifact: context
---

# Context

The person running the command owns the Pinata account. `PINATA_JWT` and `PINATA_GATEWAY` come from their environment. This change does not read a CorvidLabs key.

Public notes are the `ALGT` frames already measured in `docs/onchain-git-remote.md`. A frame is 51 bytes plus payload. A public chunk holds 4,045 payload bytes. The fee is `minFee + surcharge`, with the surcharge from PROTOCOL.md section 10.3. LocalNet here is algod `127.0.0.1:4001`, kmd `127.0.0.1:4002`, and indexer `127.0.0.1:8980`.

The writer key and the mailbox address stay in `.algit/`, which is gitignored. The page reads the clone on disk. It does not ask the browser to talk to the node.

0xLeif is the scope approver and the implementation reviewer for this change.
