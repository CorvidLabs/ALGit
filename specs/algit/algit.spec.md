---
module: algit
version: 2
status: draft
files:
  - py/algit/__init__.py
  - py/algit/__main__.py
  - py/algit/command.py
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

## Invariants

A public note is an ALGT frame of version 1. The sha1 of a stored canonical object is the object id in its frame. A push prints its fee before it submits. A MainNet quote submits nothing. A blob over 256 KiB is pinned with the caller's JWT before any note is funded. The program contains no Pinata credential of its own. The page binds to 127.0.0.1.

## Behavioral Examples

A one-commit repository becomes one set of object notes plus one ref note. Materializing those notes produces a bare repository whose git fsck exits 0 and whose branch points at the same commit. When the mailbox has more than one branch, the work tree checks out the branch that is not an ancestor of another branch, and a slash in that name is kept. Asking for a MainNet quote prints microALGO and ALGO and leaves the chain untouched. A blob of 256 KiB plus one byte is posted to the caller's Pinata gateway. The page returns the text of a file from the clone and the diff of its newest commit.

## Error Cases

The push stops before funding when a blob is over 256 KiB and PINATA_JWT or PINATA_GATEWAY is empty. The push stops when the named path is not a git repository. The clone stops when the indexer returns no ALGT notes for the mailbox. The page refuses a path that escapes the repository. A note longer than 4,096 bytes is rejected before it is signed.

## Dependencies

Python 3.11 or newer. py-algorand-sdk 2.12, because 2.11.1 rejects a note over 1,024 bytes. The git binary. A LocalNet sandbox for a push or a clone. The caller's PINATA_JWT and PINATA_GATEWAY only when a blob exceeds 256 KiB. No CorvidLabs service account.
## Change Log

| Date | Change |
|------|--------|
| 2026-10-25 | push-this-repository-to-localnet-and-read-it-in-a-local-page: Push this repository to LocalNet and read it in a local page |
| 2026-10-25 | check-out-a-branch-whose-name-contains-a-slash: Check out a branch whose name contains a slash |
