# Lesson bundle — check-out-a-branch-whose-name-contains-a-slash

Material for folding this change's lessons into each affected module's lesson file.
Synthesise from what actually happened below; do not restate the change description.

## What this change was

- **Title**: Check out a branch whose name contains a slash
- **Kind**: BugFix
- **Specs**: algit
- **Paths**: py/algit/command.py, tests/test_remote.py
- **Acceptance**: I can clone a mailbox whose branch name contains a slash, and the work tree is on that branch.

## Evidence

- Verification commit: `15253569518540602bc2fcb681eb89c175c5e286`
- Base commit: `3202adc30119bf99604246b377b26865e9b5dabe`
- Verified by: `specsync check --spec algit`

## From the change's context.md

# Context

`algit clone` of this repository failed. The mailbox held `refs/heads/leif/localnet-page`, and the checkout used only the last path segment, `localnet-page`. Git then reported that remote branch was missing.

The work tree should open the branch that is not an ancestor of another branch on the mailbox. A slash in the name is part of the name. `main` on this repository is the older commit, so the checkout is `leif/localnet-page`.

## From the change's testing.md

# Testing

`tests/test_remote.py` builds a repository with `main` and `feature/slash`, materializes the notes, and checks out the work tree. The branch name is `feature/slash` and the commit is the slash-branch tip.

## Requirement evidence

| Requirement | Evidence |
| --- | --- |
| REQ-algit-3 | tests/test_remote.py test_checkout_keeps_a_slash_in_the_branch_name |

## Where these lessons go

- `specs/algit/context.md`
