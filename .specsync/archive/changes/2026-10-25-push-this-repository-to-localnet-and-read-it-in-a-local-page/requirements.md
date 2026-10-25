---
change: push-this-repository-to-localnet-and-read-it-in-a-local-page
artifact: requirements
---

# Requirements

### REQ-algit-1

The program SHALL push the commits of a git repository onto Algorand LocalNet with one command.

Acceptance Criteria
- A temporary repository can be planned into notes and rebuilt with git fsck.
- When LocalNet is running, that same command pays the notes onto a mailbox.

### REQ-algit-2

The program SHALL show the MainNet cost of a push, in microALGO and ALGO, and SHALL spend nothing while doing so.

Acceptance Criteria
- Asking for a MainNet quote prints the fee and does not submit a transaction.

### REQ-algit-3

The program SHALL clone a mailbox back into a git repository that git fsck accepts.

Acceptance Criteria
- Notes from a planned repository materialize to a repository whose git fsck exits 0.
- A LocalNet round trip, when the sandbox is up, checks out the same commit that was pushed.

### REQ-algit-4

The program SHALL serve a page on the machine it is run on, and that page SHALL show the commits, the files, and the diff of a commit.

Acceptance Criteria
- The page is served on 127.0.0.1.
- A file from the cloned repository is readable from that page.
- The diff of the latest commit is readable from that page.

### REQ-algit-5

The program SHALL pin each blob larger than 256 KiB to the Pinata account in PINATA_JWT and publish it through PINATA_GATEWAY.

Acceptance Criteria
- A blob over 256 KiB is uploaded with the Authorization header taken from PINATA_JWT.
- The push stops before any note is sent when that variable is unset.

### REQ-algit-6

The program SHALL ship with no CorvidLabs Pinata account of its own.

Acceptance Criteria
- The Python program contains no Pinata JWT and no CorvidLabs gateway host.

### REQ-algit-7

The push, the clone, the pin, and the page SHALL be one Python program.

Acceptance Criteria
- `python -m algit` is the only command, and it implements push, clone, and serve.
