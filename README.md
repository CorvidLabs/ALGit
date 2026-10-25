# ALGit

Pins files CorvidLabs already publishes to the CorvidLabs Pinata account.

You run it on your machine, against files you already have. The API key stays in `PINATA_JWT`. There is no website, no upload form, and no server.

## Stack

TypeScript on Bun. The Pinata client is the `pinata` package. The command is `algit pin`.

AlgoNest is a different repo. It re-pins image and metadata files for NFTs that already exist. This repo does not change AlgoNest, `swift-pinata`, or `typescript-pinata`.

The on-chain git remote was measured and left unbuilt. That record is in [docs/onchain-git-remote.md](docs/onchain-git-remote.md).

## Free plan

The default stop matches Pinata Free: 500 files, 1 GB of storage, 10 GB of bandwidth, 10,000 requests, and 1 gateway. One batch over 500 files or 1 GB is refused, and nothing is uploaded. `--paid` lifts that stop for the Picnic plan (1 TB, 10 million files).

Bandwidth and request use are on the Pinata usage page. This command only counts the files in the batch you name.

## Use

```bash
bun install
cp .env.example .env
# fill PINATA_JWT and PINATA_GATEWAY, then:
export PINATA_JWT=...
export PINATA_GATEWAY=your-gateway.mypinata.cloud
bun run algit pin ./some-file.png ./some-directory
```

Each line is `cid`, bytes, gateway URL, and the local path.

```bash
bun test
bun run typecheck
```

## License

MIT
