# Lesson bundle — browse-files-as-folders-and-read-a-commit-as-the-files-it-changed

Material for folding this change's lessons into each affected module's lesson file.
Synthesise from what actually happened below; do not restate the change description.

## What this change was

- **Title**: Browse files as folders and read a commit as the files it changed
- **Kind**: BugFix
- **Specs**: algit
- **Paths**: py/algit/command.py, tests/test_remote.py
- **Acceptance**: I can browse the repository as folders.
- **Acceptance**: I can open a file on its own.
- **Acceptance**: I can read a commit as the files it changed.

## Evidence

- Verification commit: `1548f750dac3ca9986715104bbc75b14b733db43`
- Base commit: `72a6bd9c029567db70a2508efb780070e30d9571`
- Verified by: `specsync check --spec algit`

## From the change's context.md

# Context

The page listed every file as its full path, so a long archive name wrapped down the rail and pushed the commits off the screen. Opening a commit printed the raw patch, which for a lifecycle commit is a wall of JSON.

Folders use `details` and `summary`. A file shows its own name, with the path broken at each slash above it. A commit shows the files it changed. Choosing one of those files shows that file's diff. The two panes scroll on their own. A binary file is named by its size instead of dumped.

## From the change's testing.md

# Testing

`tests/test_remote.py` builds a repository with `README.md` and `src/a.txt`, fetches the overview tree and the commit file list, and checks that the page contains a folder disclosure and a file finder.

## Requirement evidence

| Requirement | Evidence |
| --- | --- |
| REQ-algit-4 | tests/test_remote.py test_page_shows_file_and_diff_on_loopback |

## Where these lessons go

- `specs/algit/context.md`
