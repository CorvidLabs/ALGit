---
change: push-this-repository-to-localnet-and-read-it-in-a-local-page
artifact: plan
---

# Plan

## Approach

One Python package, `py/algit`, pushes a repository as public `ALGT` note frames, clones those notes back into git, pins a blob over 256 KiB to the Pinata account in the environment, and serves a local page over the clone. LocalNet is the network the push spends on. MainNet is a quote. The first repository shown is this one.

## Out of scope

A private AlgoChat mailbox. Delta compression. A MainNet send. Issues, pull requests, and CI logs. Replacing the existing TypeScript pin files. Rewriting this repository's commits, because none of its blobs are over 256 KiB.

## Steps

1. Point spec-sync at `py/` and add the Python package.
2. Plan canonical git objects, chunk them into public notes, and price them with the section 10.3 fee.
3. On LocalNet, fund a writer from the sandbox dispenser, print the fee, then pay the notes to a new mailbox.
4. Read the mailbox back through the indexer, rebuild the git objects, and run git fsck.
5. Pin any blob over 256 KiB with PINATA_JWT before a note is sent, and stop if that variable is missing.
6. Serve the clone on 127.0.0.1 with the commits, the files, and a commit diff.
7. Push this repository, open the page, and record the mailbox.

## Risks

The Homebrew algosdk is 2.11.1 and rejects a note over 1,024 bytes. The program depends on py-algorand-sdk 2.12.0. The indexer can lag the algod round, so the clone waits until the indexer has reached the push. A zero-amount payment requires the mailbox to already hold the minimum balance, so the dispenser funds the mailbox first.

## Constraints consulted

none
