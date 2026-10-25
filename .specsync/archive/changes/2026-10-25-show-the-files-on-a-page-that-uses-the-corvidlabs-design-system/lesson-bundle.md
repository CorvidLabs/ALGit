# Lesson bundle — show-the-files-on-a-page-that-uses-the-corvidlabs-design-system

Material for folding this change's lessons into each affected module's lesson file.
Synthesise from what actually happened below; do not restate the change description.

## What this change was

- **Title**: Show the files on a page that uses the CorvidLabs design system
- **Kind**: BugFix
- **Specs**: algit
- **Paths**: py/algit/command.py, tests/test_remote.py, py/algit/brand
- **Acceptance**: The page I open shows the files and the commits.
- **Acceptance**: The page uses the CorvidLabs design system.

## Evidence

- Verification commit: `c721321bba5a6444b40869345c52705fac847ac5`
- Base commit: `fb57e4464108ec533230761f33aeae3db7066fad`
- Verified by: `specsync check --spec algit`

## From the change's context.md

# Context

The page at 127.0.0.1 showed the ALGit rail and the words Files and Commits, and nothing else. The lists are filled by a script that uses `await` at the top level of a classic script. Browsers reject that script, so the files never appear.

The page also used its own navy rail, rust accent, and Charter type. CorvidLabs pages use the design system in CorvidLabs/design-system: `assets/tokens.css`, `assets/theme.js`, the sun/moon toggle, Schibsted Grotesk, and Spline Sans Mono. The accent is the sheen. The files are copied into this program and served with the page. They are not re-derived.

## From the change's testing.md

# Testing

`tests/test_remote.py` fetches the page and asserts the script is `type="module"`, that `/brand/tokens.css` is linked and contains `--paper`, and that a file and a diff still load. The browser check is a reload of http://127.0.0.1:4711/ after the server is restarted.

## Requirement evidence

| Requirement | Evidence |
| --- | --- |
| REQ-algit-4 | tests/test_remote.py test_page_shows_file_and_diff_on_loopback |

## Where these lessons go

- `specs/algit/context.md`
