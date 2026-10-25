---
change: check-out-a-branch-whose-name-contains-a-slash
artifact: context
---

# Context

`algit clone` of this repository failed. The mailbox held `refs/heads/leif/localnet-page`, and the checkout used only the last path segment, `localnet-page`. Git then reported that remote branch was missing.

The work tree should open the branch that is not an ancestor of another branch on the mailbox. A slash in the name is part of the name. `main` on this repository is the older commit, so the checkout is `leif/localnet-page`.
