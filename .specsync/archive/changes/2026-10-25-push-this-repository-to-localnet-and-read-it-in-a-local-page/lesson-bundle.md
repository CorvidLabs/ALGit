# Lesson bundle — push-this-repository-to-localnet-and-read-it-in-a-local-page

Material for folding this change's lessons into each affected module's lesson file.
Synthesise from what actually happened below; do not restate the change description.

## What this change was

- **Title**: Push this repository to LocalNet and read it in a local page
- **Kind**: Feature
- **Specs**: algit
- **Paths**: py, tests, pyproject.toml, README.md, .specsync/config.toml, .gitignore
- **Acceptance**: I can push a git repository to Algorand LocalNet with one command.
- **Acceptance**: I can ask what the same push would cost on MainNet and see the ALGO before anything is spent.
- **Acceptance**: I can clone that repository back off the chain and git fsck accepts it.
- **Acceptance**: I can start a page on my own machine and read the commits, files, and diffs of what I pushed.
- **Acceptance**: A file that is too heavy for a note is pinned to the Pinata account in my PINATA_JWT, through the gateway in my PINATA_GATEWAY.
- **Acceptance**: The command has no CorvidLabs Pinata account of its own.
- **Acceptance**: The command and the page are one Python program.

## Evidence

- Verification commit: `4b98ea8bbc860d3c55796080741903b28d1a6e26`
- Base commit: `2aee85055fb43adf616f740eb998a6781e287dc7`
- Verified by: `specsync check --spec algit`

## From the change's context.md

# Context

The person running the command owns the Pinata account. `PINATA_JWT` and `PINATA_GATEWAY` come from their environment. This change does not read a CorvidLabs key.

Public notes are the `ALGT` frames already measured in `docs/onchain-git-remote.md`. A frame is 51 bytes plus payload. A public chunk holds 4,045 payload bytes. The fee is `minFee + surcharge`, with the surcharge from PROTOCOL.md section 10.3. LocalNet here is algod `127.0.0.1:4001`, kmd `127.0.0.1:4002`, and indexer `127.0.0.1:8980`.

The writer key and the mailbox address stay in `.algit/`, which is gitignored. The page reads the clone on disk. It does not ask the browser to talk to the node.

0xLeif is the scope approver and the implementation reviewer for this change.

## From the change's design.md

# Design

The page is a local reader for one repository that was just recovered from payment notes. The person using it already knows the repository. The page's job is to show the commit, the files, and the diff without looking like a hosted forge.

The memorable piece is the left rail: a dark blue-green column with the mailbox address set in wide lines, and the branch name in dry rust. Everything to the right is the commit message in Charter, then the file or the diff in a plain preformatted block.

Color. Field `#e4ebf0`. Ink `#17202b`. Rail `#1b3040`. Rail text `#e7eef3`. Rust `#b8431f`, used only for the branch name. Line `#c5d2db`.

Type. Commit message in Charter, then Iowan Old Style, then Georgia. Chrome in Avenir Next, then Segoe UI. Object ids and file paths in a monospace face because they are identifiers.

Layout. A two-track grid. The rail is `16rem` and the reading column is the rest. Under 40rem the rail stacks above the reading column. The file list is a list of links. The reading column is one commit at a time.

The page does not use cards, a cream background, or a label above every heading. A skip link is the first focusable control. Focus uses an outline. File bytes and diffs are inserted as text, never as HTML.

## From the change's testing.md

# Testing

`python -m unittest discover -s tests` covers the fee, the plan round trip, the MainNet quote, the personal pin, the absence of a CorvidLabs key, and the local page. A LocalNet push runs when algod answers on 127.0.0.1:4001 and is skipped otherwise. `specsync check --spec algit` is the contract check.

## Requirement evidence

| Requirement | Evidence |
| --- | --- |
| REQ-algit-1 | tests/test_remote.py plans a repository and, when LocalNet is up, pushes it |
| REQ-algit-2 | tests/test_remote.py asserts a MainNet quote prints the fee and submits nothing |
| REQ-algit-3 | tests/test_remote.py materializes notes and runs git fsck |
| REQ-algit-4 | tests/test_remote.py fetches the page, a file, and a diff from 127.0.0.1 |
| REQ-algit-5 | tests/test_remote.py records the Authorization header of a pin and the refusal when PINATA_JWT is unset |
| REQ-algit-6 | tests/test_remote.py reads the Python sources and finds no CorvidLabs Pinata key |
| REQ-algit-7 | tests/test_remote.py runs python -m algit for push, clone, and serve |

## Where these lessons go

- `specs/algit/context.md`
