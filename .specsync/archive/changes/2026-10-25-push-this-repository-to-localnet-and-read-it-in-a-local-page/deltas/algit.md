## ADDED

### REQUIREMENT REQ-algit-1

The program SHALL push the commits of a git repository onto Algorand LocalNet with one command.

Acceptance Criteria
- A temporary repository can be planned into notes and rebuilt with git fsck.
- When LocalNet is running, that same command pays the notes onto a mailbox.

### REQUIREMENT REQ-algit-2

The program SHALL show the MainNet cost of a push, in microALGO and ALGO, and SHALL spend nothing while doing so.

Acceptance Criteria
- Asking for a MainNet quote prints the fee and does not submit a transaction.

### REQUIREMENT REQ-algit-3

The program SHALL clone a mailbox back into a git repository that git fsck accepts.

Acceptance Criteria
- Notes from a planned repository materialize to a repository whose git fsck exits 0.
- A LocalNet round trip, when the sandbox is up, checks out the same commit that was pushed.

### REQUIREMENT REQ-algit-4

The program SHALL serve a page on the machine it is run on, and that page SHALL show the commits, the files, and the diff of a commit.

Acceptance Criteria
- The page is served on 127.0.0.1.
- A file from the cloned repository is readable from that page.
- The diff of the latest commit is readable from that page.

### REQUIREMENT REQ-algit-5

The program SHALL pin each blob larger than 256 KiB to the Pinata account in PINATA_JWT and publish it through PINATA_GATEWAY.

Acceptance Criteria
- A blob over 256 KiB is uploaded with the Authorization header taken from PINATA_JWT.
- The push stops before any note is sent when that variable is unset.

### REQUIREMENT REQ-algit-6

The program SHALL ship with no CorvidLabs Pinata account of its own.

Acceptance Criteria
- The Python program contains no Pinata JWT and no CorvidLabs gateway host.

### REQUIREMENT REQ-algit-7

The push, the clone, the pin, and the page SHALL be one Python program.

Acceptance Criteria
- `python -m algit` is the only command, and it implements push, clone, and serve.

### SPEC SECTION Purpose

Push a git repository onto Algorand LocalNet, quote the same push on MainNet without spending, clone the mailbox back into a repository git fsck accepts, pin a blob over 256 KiB to the caller's Pinata account, and serve a page on 127.0.0.1 that shows the commits, the files, and a commit diff.

### SPEC SECTION Public API

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

### SPEC SECTION Invariants

A public note is an ALGT frame of version 1. The sha1 of a stored canonical object is the object id in its frame. A push prints its fee before it submits. A MainNet quote submits nothing. A blob over 256 KiB is pinned with the caller's JWT before any note is funded. The program contains no Pinata credential of its own. The page binds to 127.0.0.1.

### SPEC SECTION Behavioral Examples

A one-commit repository becomes one set of object notes plus one ref note. Materializing those notes produces a bare repository whose git fsck exits 0 and whose branch points at the same commit. Asking for a MainNet quote prints microALGO and ALGO and leaves the chain untouched. A blob of 256 KiB plus one byte is posted to the caller's Pinata gateway. The page returns the text of a file from the clone and the diff of its newest commit.

### SPEC SECTION Error Cases

The push stops before funding when a blob is over 256 KiB and PINATA_JWT or PINATA_GATEWAY is empty. The push stops when the named path is not a git repository. The clone stops when the indexer returns no ALGT notes for the mailbox. The page refuses a path that escapes the repository. A note longer than 4,096 bytes is rejected before it is signed.

### SPEC SECTION Dependencies

Python 3.11 or newer. py-algorand-sdk 2.12, because 2.11.1 rejects a note over 1,024 bytes. The git binary. A LocalNet sandbox for a push or a clone. The caller's PINATA_JWT and PINATA_GATEWAY only when a blob exceeds 256 KiB. No CorvidLabs service account.
