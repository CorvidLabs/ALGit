---
change: browse-files-as-folders-and-read-a-commit-as-the-files-it-changed
artifact: requirements
---

# Requirements

### REQ-algit-4

The page SHALL present the repository as folders, SHALL open one file on its own, and SHALL show a commit as the files it changed.

Acceptance Criteria
- The overview includes a nested tree, so `src/a.txt` is a file inside a folder named `src`.
- A commit response names each changed path.
- The page includes a folder disclosure and a file finder.
