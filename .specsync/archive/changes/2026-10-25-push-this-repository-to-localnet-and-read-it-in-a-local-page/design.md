---
change: push-this-repository-to-localnet-and-read-it-in-a-local-page
artifact: design
---

# Design

The page is a local reader for one repository that was just recovered from payment notes. The person using it already knows the repository. The page's job is to show the commit, the files, and the diff without looking like a hosted forge.

The memorable piece is the left rail: a dark blue-green column with the mailbox address set in wide lines, and the branch name in dry rust. Everything to the right is the commit message in Charter, then the file or the diff in a plain preformatted block.

Color. Field `#e4ebf0`. Ink `#17202b`. Rail `#1b3040`. Rail text `#e7eef3`. Rust `#b8431f`, used only for the branch name. Line `#c5d2db`.

Type. Commit message in Charter, then Iowan Old Style, then Georgia. Chrome in Avenir Next, then Segoe UI. Object ids and file paths in a monospace face because they are identifiers.

Layout. A two-track grid. The rail is `16rem` and the reading column is the rest. Under 40rem the rail stacks above the reading column. The file list is a list of links. The reading column is one commit at a time.

The page does not use cards, a cream background, or a label above every heading. A skip link is the first focusable control. Focus uses an outline. File bytes and diffs are inserted as text, never as HTML.
