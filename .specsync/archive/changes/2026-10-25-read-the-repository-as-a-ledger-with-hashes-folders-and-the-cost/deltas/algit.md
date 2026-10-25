## MODIFIED

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
| `blob_sizes` | function | Map each file path to its size in bytes. |
| `file_tree` | function | Nest those paths into folders, with a size on every node. |
| `commit_list` | function | List commits with a count of the paths each one changed. |
| `overview` | function | The branch, the tree, the bytes, the commits, and the receipt account. |

### SPEC SECTION Behavioral Examples

A one-commit repository becomes one set of object notes plus one ref note. Materializing those notes produces a bare repository whose git fsck exits 0 and whose branch points at the same commit. When the mailbox has more than one branch, the work tree checks out the branch that is not an ancestor of another branch, and a slash in that name is kept. Asking for a MainNet quote prints microALGO and ALGO and leaves the chain untouched. A blob of 256 KiB plus one byte is posted to the caller's Pinata gateway. The page loads `/brand/page.js`, which is valid JavaScript, plus the CorvidLabs tokens, the sun/moon toggle, Schibsted Grotesk, and Spline Sans Mono. Files are folders. A folder whose name starts with a dot starts closed. Each file shows its size. A commit shows a short hash and then the files it changed. The strip shows the ALGO the notes cost, the microALGO, the note count, the round span, and the total size. Pressing `/` focuses the file finder.
