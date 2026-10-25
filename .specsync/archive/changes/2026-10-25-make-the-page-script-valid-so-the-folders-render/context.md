---
change: make-the-page-script-valid-so-the-folders-render
artifact: context
---

# Context

The browser showed the ALGit shell and then nothing. The page script is stored in a Python string. A `\n` in that string is a real line break by the time the browser sees it, so `split("\n")` is not a JavaScript string and the whole module is discarded. The folders, commits, and file never run.

The script now splits on `String.fromCharCode(10)`. A failure after the script parses is written into the page instead of leaving it blank.
