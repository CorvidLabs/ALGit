---
change: show-the-files-on-a-page-that-uses-the-corvidlabs-design-system
artifact: context
---

# Context

The page at 127.0.0.1 showed the ALGit rail and the words Files and Commits, and nothing else. The lists are filled by a script that uses `await` at the top level of a classic script. Browsers reject that script, so the files never appear.

The page also used its own navy rail, rust accent, and Charter type. CorvidLabs pages use the design system in CorvidLabs/design-system: `assets/tokens.css`, `assets/theme.js`, the sun/moon toggle, Schibsted Grotesk, and Spline Sans Mono. The accent is the sheen. The files are copied into this program and served with the page. They are not re-derived.
