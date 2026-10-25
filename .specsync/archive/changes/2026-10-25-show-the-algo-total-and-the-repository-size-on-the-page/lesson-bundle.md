# Lesson bundle — show-the-algo-total-and-the-repository-size-on-the-page

Material for folding this change's lessons into each affected module's lesson file.
Synthesise from what actually happened below; do not restate the change description.

## What this change was

- **Title**: Show the ALGO total and the repository size on the page
- **Kind**: Feature
- **Specs**: algit
- **Paths**: py/algit/command.py, tests/test_remote.py
- **Acceptance**: I can see the total ALGO, the note count, the rounds, and the size of the repository.

## Evidence

- Verification commit: `7a0a8b3307cf938d7b04b9e8fccf8e88e623ce7a`
- Base commit: `e47567fd8ff21c8aeae58084c27bbbe89aa5be62`
- Verified by: `specsync check --spec algit`

## From the change's context.md

# Context

The page showed the repository and hid what the push cost. The receipt already records the note fee, the note count, and the rounds. The file sizes are in git. The page now puts those numbers in a strip: ALGO, microALGO, notes, size, files, commits, and the round span. Each file shows its own size.

## From the change's testing.md

# Testing

`tests/test_remote.py` checks that the overview byte count is above zero and that the page contains the facts strip. Headless Chrome on the LocalNet clone shows 0.265338 ALGO, 243 notes, and 265.7 KiB.

## Requirement evidence

| Requirement | Evidence |
| --- | --- |
| REQ-algit-4 | tests/test_remote.py test_page_shows_file_and_diff_on_loopback |

## Where these lessons go

- `specs/algit/context.md`
