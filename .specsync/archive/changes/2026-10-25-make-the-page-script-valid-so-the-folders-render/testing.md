---
change: make-the-page-script-valid-so-the-folders-render
artifact: testing
---

# Testing

The served module parses with `node --check`. Headless Chrome loads http://127.0.0.1:4711/ and the document contains the folder disclosures and the text `README.md`. `tests/test_remote.py` still fetches the page, the tree, and a file.

## Requirement evidence

| Requirement | Evidence |
| --- | --- |
| REQ-algit-4 | tests/test_remote.py test_page_shows_file_and_diff_on_loopback |
