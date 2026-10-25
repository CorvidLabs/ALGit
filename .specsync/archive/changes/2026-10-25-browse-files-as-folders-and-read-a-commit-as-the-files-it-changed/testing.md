---
change: browse-files-as-folders-and-read-a-commit-as-the-files-it-changed
artifact: testing
---

# Testing

`tests/test_remote.py` builds a repository with `README.md` and `src/a.txt`, fetches the overview tree and the commit file list, and checks that the page contains a folder disclosure and a file finder.

## Requirement evidence

| Requirement | Evidence |
| --- | --- |
| REQ-algit-4 | tests/test_remote.py test_page_shows_file_and_diff_on_loopback |
