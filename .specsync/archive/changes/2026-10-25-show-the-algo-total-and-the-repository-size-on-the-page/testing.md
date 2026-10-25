---
change: show-the-algo-total-and-the-repository-size-on-the-page
artifact: testing
---

# Testing

`tests/test_remote.py` checks that the overview byte count is above zero and that the page contains the facts strip. Headless Chrome on the LocalNet clone shows 0.265338 ALGO, 243 notes, and 265.7 KiB.

## Requirement evidence

| Requirement | Evidence |
| --- | --- |
| REQ-algit-4 | tests/test_remote.py test_page_shows_file_and_diff_on_loopback |
