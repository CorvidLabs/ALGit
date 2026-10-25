---
change: check-out-a-branch-whose-name-contains-a-slash
artifact: requirements
---

# Requirements

### REQ-algit-3

The program SHALL clone a mailbox back into a git repository that git fsck accepts, and SHALL check out a branch whose name contains a slash.

Acceptance Criteria
- A repository with `feature/slash` materializes and the work tree is on `feature/slash`.
