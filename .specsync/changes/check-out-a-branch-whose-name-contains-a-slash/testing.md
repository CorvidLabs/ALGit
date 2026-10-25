---
change: check-out-a-branch-whose-name-contains-a-slash
artifact: testing
---

# Testing

`tests/test_remote.py` builds a repository with `main` and `feature/slash`, materializes the notes, and checks out the work tree. The branch name is `feature/slash` and the commit is the slash-branch tip.

## Requirement evidence

| Requirement | Evidence |
| --- | --- |
| REQ-algit-3 | tests/test_remote.py test_checkout_keeps_a_slash_in_the_branch_name |
