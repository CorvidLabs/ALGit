---
change: push-this-repository-to-localnet-and-read-it-in-a-local-page
artifact: testing
---

# Testing

`python -m unittest discover -s tests` covers the fee, the plan round trip, the MainNet quote, the personal pin, the absence of a CorvidLabs key, and the local page. A LocalNet push runs when algod answers on 127.0.0.1:4001 and is skipped otherwise. `specsync check --spec algit` is the contract check.

## Requirement evidence

| Requirement | Evidence |
| --- | --- |
| REQ-algit-1 | tests/test_remote.py plans a repository and, when LocalNet is up, pushes it |
| REQ-algit-2 | tests/test_remote.py asserts a MainNet quote prints the fee and submits nothing |
| REQ-algit-3 | tests/test_remote.py materializes notes and runs git fsck |
| REQ-algit-4 | tests/test_remote.py fetches the page, a file, and a diff from 127.0.0.1 |
| REQ-algit-5 | tests/test_remote.py records the Authorization header of a pin and the refusal when PINATA_JWT is unset |
| REQ-algit-6 | tests/test_remote.py reads the Python sources and finds no CorvidLabs Pinata key |
| REQ-algit-7 | tests/test_remote.py runs python -m algit for push, clone, and serve |
