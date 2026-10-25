---
change: show-the-algo-total-and-the-repository-size-on-the-page
artifact: plan
---

# Plan

## Approach

Read the push receipt for the note fee, the note count, and the rounds. Measure file bytes with `git ls-tree -l`. Show both in a strip on the page, and show each file's size beside its name.

## Out of scope

A second push. MainNet spending. Rewriting the fee rule.

## Steps

1. Pass the receipt into the page.
2. Add bytes to the overview and to each file in the tree.
3. Render the facts strip.
4. Confirm the LocalNet clone shows 0.265338 ALGO and 265.7 KiB.

## Risks

The receipt is the note fee. It does not include the sandbox dispenser payment that created the mailbox. The strip says so by naming the notes.

## Constraints consulted

none
