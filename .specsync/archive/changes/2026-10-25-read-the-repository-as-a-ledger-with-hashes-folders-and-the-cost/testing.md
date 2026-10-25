---
change: read-the-repository-as-a-ledger-with-hashes-folders-and-the-cost
artifact: testing
---

# Testing

`tests/test_viewdata.py` checks the tree, the byte sum, and a commit path count. `tests/test_remote.py` fetches `/brand/page.js` and checks that it builds a details element. Headless Chrome on the LocalNet clone shows 0.265338 ALGO, folder disclosures, and 12 commit hashes.

## Requirement evidence

| Requirement | Evidence |
| --- | --- |
| REQ-algit-4 | tests/test_remote.py test_page_shows_file_and_diff_on_loopback and tests/test_viewdata.py |
