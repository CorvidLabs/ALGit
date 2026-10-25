# ALGit

ALGit pushes a git repository to Algorand and lets you read it in a page on your own machine.

You run it locally. A push spends on LocalNet, and only after it has printed the fee and you pass `--yes`. Asking for MainNet prints the same cost and sends nothing. A blob over 256 KiB is pinned to the Pinata account in your `PINATA_JWT`, through `PINATA_GATEWAY`. The command has no Pinata account of its own.

The page listens on `127.0.0.1`. It shows the commits, the files, and the diff of a commit.

The on-chain measurement that came before this command is in [docs/onchain-git-remote.md](docs/onchain-git-remote.md).

## Use

```bash
python3 -m venv .venv
.venv/bin/pip install -e .
export PINATA_JWT=...            # only if a blob is over 256 KiB
export PINATA_GATEWAY=your.gateway

.venv/bin/algit push --repo . --network mainnet
.venv/bin/algit push --repo . --yes
.venv/bin/algit clone <mailbox> --into .algit/work
.venv/bin/algit serve --repo .algit/work
```

`push` prints the mailbox. `clone` checks the result with `git fsck`. `serve` prints a `http://127.0.0.1:` address.

```bash
.venv/bin/python -m unittest discover -s tests
```

## License

MIT
