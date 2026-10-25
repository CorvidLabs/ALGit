---
change: read-the-repository-as-a-ledger-with-hashes-folders-and-the-cost
artifact: requirements
---

# Requirements

### REQ-algit-4

The page SHALL load a valid script, show the cost and the size, and let a person open a folder, a file, and a commit by its hash.

Acceptance Criteria
- `/brand/page.js` parses and builds folders with details and summary.
- The overview tree nests `src/a.txt` and reports bytes.
- A commit record includes how many paths it changed.
