# Lesson bundle — make-the-page-script-valid-so-the-folders-render

Material for folding this change's lessons into each affected module's lesson file.
Synthesise from what actually happened below; do not restate the change description.

## What this change was

- **Title**: Make the page script valid so the folders render
- **Kind**: BugFix
- **Specs**: algit
- **Paths**: py/algit/command.py
- **Acceptance**: The page script is valid JavaScript.
- **Acceptance**: A browser shows the folders and the open file.

## Evidence

- Verification commit: `55a8635944348ae7c123ea88465a952adfebfcb2`
- Base commit: `e3627bb888a51b19a8b417ea95ca79e423c92d22`
- Verified by: `specsync check --spec algit`

## From the change's context.md

# Context

The browser showed the ALGit shell and then nothing. The page script is stored in a Python string. A `\n` in that string is a real line break by the time the browser sees it, so `split("\n")` is not a JavaScript string and the whole module is discarded. The folders, commits, and file never run.

The script now splits on `String.fromCharCode(10)`. A failure after the script parses is written into the page instead of leaving it blank.

## From the change's testing.md

# Testing

The served module parses with `node --check`. Headless Chrome loads http://127.0.0.1:4711/ and the document contains the folder disclosures and the text `README.md`. `tests/test_remote.py` still fetches the page, the tree, and a file.

## Requirement evidence

| Requirement | Evidence |
| --- | --- |
| REQ-algit-4 | tests/test_remote.py test_page_shows_file_and_diff_on_loopback |

## Where these lessons go

- `specs/algit/context.md`
