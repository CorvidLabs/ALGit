---
change: read-the-repository-as-a-ledger-with-hashes-folders-and-the-cost
artifact: plan
---

# Plan

## Approach

Move the page script into its own file. Build the overview in `viewdata.py`. Serve both. Keep the design-system tokens.

## Out of scope

A new push onto LocalNet. Syntax highlighting beyond a comment and a keyword. MainNet sending.

## Steps

1. Add `viewdata.overview`.
2. Add `page.js` and `page.css` and point the page at them.
3. Check the script parses and headless Chrome shows the ALGO total, the folders, and the commit hashes.

## Risks

An inline script inside a Python string will break again if a newline is written as `\n`. The script file avoids that.

## Constraints consulted

none
