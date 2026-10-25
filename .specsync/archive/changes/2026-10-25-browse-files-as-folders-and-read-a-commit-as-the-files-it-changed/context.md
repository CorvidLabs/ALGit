---
change: browse-files-as-folders-and-read-a-commit-as-the-files-it-changed
artifact: context
---

# Context

The page listed every file as its full path, so a long archive name wrapped down the rail and pushed the commits off the screen. Opening a commit printed the raw patch, which for a lifecycle commit is a wall of JSON.

Folders use `details` and `summary`. A file shows its own name, with the path broken at each slash above it. A commit shows the files it changed. Choosing one of those files shows that file's diff. The two panes scroll on their own. A binary file is named by its size instead of dumped.
