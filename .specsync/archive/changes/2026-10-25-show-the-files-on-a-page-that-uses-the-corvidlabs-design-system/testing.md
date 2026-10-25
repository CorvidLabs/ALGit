---
change: show-the-files-on-a-page-that-uses-the-corvidlabs-design-system
artifact: testing
---

# Testing

`tests/test_remote.py` fetches the page and asserts the script is `type="module"`, that `/brand/tokens.css` is linked and contains `--paper`, and that a file and a diff still load. The browser check is a reload of http://127.0.0.1:4711/ after the server is restarted.

## Requirement evidence

| Requirement | Evidence |
| --- | --- |
| REQ-algit-4 | tests/test_remote.py test_page_shows_file_and_diff_on_loopback |
