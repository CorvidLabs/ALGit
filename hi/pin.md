---
hi: 1
families: [PIN]
---

# Pin

## Intent

Notes are a poor place for a large file. Those bytes go to the Pinata account the person already has. The command never carries a CorvidLabs key.


## Criteria

- **PIN-1**  A file that is too heavy for a note is pinned to the Pinata account in my PINATA_JWT, through the gateway in my PINATA_GATEWAY.
- **PIN-2**  The command has no CorvidLabs Pinata account of its own.
