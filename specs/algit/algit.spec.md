---
module: algit
version: 7
status: draft
files:
  - py/algit/__init__.py
  - py/algit/__main__.py
  - py/algit/command.py
  - py/algit/brand/tokens.css
  - py/algit/brand/theme.js
  - py/algit/brand/logo-mark.svg
  - py/algit/brand/page.css
  - py/algit/brand/page.js
  - py/algit/viewdata.py
---

# algit

## Purpose

Push a git repository onto Algorand LocalNet, quote the same push on MainNet without spending, clone the mailbox back into a repository git fsck accepts, pin a blob over 256 KiB to the caller's Pinata account, and serve a page on 127.0.0.1 that shows the commits, the files, and a commit diff.

## Public API

| Symbol | Kind | Description |
| --- | --- | --- |
| `fee_for_note` | function | MicroALGO fee for one note under the section 10.3 rule. |
| `plan_repository` | function | Canonical objects and branch refs for a repository, with heavy blobs pinned. |
| `materialize_frames` | function | Rebuild a git directory from ALGT frames and report git fsck. |
| `quote_push` | function | Fee for a repository at a given minimum fee. Spends nothing. |
| `push_localnet` | function | Print the fee, then pay the notes to a new LocalNet mailbox. |
| `clone_mailbox` | function | Read a mailbox from the indexer and materialize it. |
| `pin_heavy_blobs` | function | Upload blobs over 256 KiB with PINATA_JWT. |
| `serve` | function | Serve the local page for a cloned repository. |
| `main` | function | Command line entry for push, clone, and serve. |
| `blob_sizes` | function | Map each file path to its size in bytes. |
| `file_tree` | function | Nest those paths into folders, with a size on every node. |
| `commit_list` | function | List commits with a count of the paths each one changed. |
| `overview` | function | The branch, the tree, the bytes, the commits, and the receipt account. |
| `note_fee` | function | MicroALGO for one note under the same integer rule as the push. |
| `object_note_fees` | function | MicroALGO and note count for one canonical git object. |
| `commit_cost` | function | MicroALGO for the objects a commit introduces. Ref notes are not included. |

## Invariants

A public note is an ALGT frame of version 1. The sha1 of a stored canonical object is the object id in its frame. A push prints its fee before it submits. A MainNet quote submits nothing. A blob over 256 KiB is pinned with the caller's JWT before any note is funded. The program contains no Pinata credential of its own. The page binds to 127.0.0.1.

## Behavioral Examples

A one-commit repository becomes one set of object notes plus one ref note. Materializing those notes produces a bare repository whose git fsck exits 0 and whose branch points at the same commit. When the mailbox has more than one branch, the work tree checks out the branch that is not an ancestor of another branch, and a slash in that name is kept. Asking for a MainNet quote prints microALGO and ALGO and leaves the chain untouched. A blob of 256 KiB plus one byte is posted to the caller's Pinata gateway. The page loads `/brand/page.js`, which is valid JavaScript, plus the CorvidLabs tokens, the sun/moon toggle, Schibsted Grotesk, and Spline Sans Mono. Files are folders. A folder whose name starts with a dot starts closed. Each file shows its size. A commit shows a short hash and then the files it changed. The strip shows the ALGO the notes cost, the microALGO, the note count, the round span, and the total size. Pressing `/` focuses the file finder.

## Error Cases

The push stops before funding when a blob is over 256 KiB and PINATA_JWT or PINATA_GATEWAY is empty. The push stops when the named path is not a git repository. The clone stops when the indexer returns no ALGT notes for the mailbox. The page refuses a path that escapes the repository. A note longer than 4,096 bytes is rejected before it is signed.

## Dependencies

Python 3.11 or newer. py-algorand-sdk 2.12, because 2.11.1 rejects a note over 1,024 bytes. The git binary. A LocalNet sandbox for a push or a clone. The caller's PINATA_JWT and PINATA_GATEWAY only when a blob exceeds 256 KiB. No CorvidLabs service account.
## Change Log

| Date | Change |
|------|--------|
| 2026-10-25 | push-this-repository-to-localnet-and-read-it-in-a-local-page: Push this repository to LocalNet and read it in a local page |
| 2026-10-25 | check-out-a-branch-whose-name-contains-a-slash: Check out a branch whose name contains a slash |
| 2026-10-25 | show-the-files-on-a-page-that-uses-the-corvidlabs-design-system: Show the files on a page that uses the CorvidLabs design system |
| 2026-10-25 | browse-files-as-folders-and-read-a-commit-as-the-files-it-changed: Browse files as folders and read a commit as the files it changed |
| 2026-10-25 | make-the-page-script-valid-so-the-folders-render: Make the page script valid so the folders render |
| 2026-10-25 | show-the-algo-total-and-the-repository-size-on-the-page: Show the ALGO total and the repository size on the page |
| 2026-10-25 | read-the-repository-as-a-ledger-with-hashes-folders-and-the-cost: Read the repository as a ledger with hashes, folders, and the cost |
