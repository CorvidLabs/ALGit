# A Git remote on an AlgoChat mailbox

Measured on LocalNet, 24 October 2026. The client is `py-algorand-sdk` 2.12.0. Consensus is the LocalNet sandbox (`dockernet-v1`, algod at `127.0.0.1:4001`). No second cipher. Private bytes are AlgoChat group messages. Public bytes are raw notes.

## Recommendation

Do not build it. A private remote can work for a repository the size of `algochat`, and that is not a product we are making. Do not build a public on-chain remote. This does not replace GitHub.

Decision, 24 October 2026: leave the remote unbuilt. Confidence in making and shipping it was 20%. Confidence in leaving it unbuilt was 80%. ALGO going up was not the reason.

`site` as stored is not that remote. The public import was 290.717 ALGO. Raster images are 169.060 ALGO of the object fee. Replacing only those with CID pointers still leaves 133.442 ALGO on a private mailbox. Keeping source blobs, trees, and commits, and storing every other blob as a 72-byte CID pointer, is 40.733 ALGO private. If specsync records and the `src/data` catalogues are pointers too, it is 30.548 ALGO. Both are three to four times the `algochat` import, so neither is the first remote to build. Averages, the month series, and an 85% confidence rating on that verdict are in [site-onchain-cost.html](site-onchain-cost.html).

`algochat` is the small case. GitHub reports it at 2,433 KB. The published history is 4,298 git objects and 18.97 MB of canonical object bytes, about eight times the GitHub figure, because the chain stores inflated objects rather than a pack. Pushed as AlgoChat `0x07` notes:

| Write model | Notes | Fee | Push | Read back |
| --- | ---: | ---: | ---: | ---: |
| Content-addressed objects | 7,944 | 9.257 ALGO | 38.0 s | 32.4 s |
| Binary deltas of changed blobs | 6,320 | 7.044 ALGO | 30.3 s | 14.2 s |

Both clones passed `git fsck --full`. `refs/heads/main` came back as `963cd24d2082b4e756049f68596dfaa6e3dbd92e`, which is `origin/main`. A one-line edit was a fraction of a cent. Pushing the same commit again sent one ref note and no objects (1,000 µALGO). That is a usable private remote for a repository of a few megabytes.

`site` is the large case that was pushed. GitHub reports 538,649 KB (526 MiB). Origin plus tags is 20,709 objects and 822 MB of canonical bytes. The public object import, the only large push, was 225,869 notes, 290.717 ALGO, 606.5 seconds to write, and 87.9 seconds to read back. `git fsck --full` was clean and `refs/heads/main` was `a658383d1f968daced4eba86a0ee22d7950756b3`. The offline private plan for the same objects is 229,513 notes and 295.554 ALGO. Deltas lower the public plan to 188,354 notes and 241.301 ALGO. Those are full-blob prices. Most of the fee is images and other published bytes, priced in the HTML page. `peck`, `Roost`, `3md`, and `Talon` were not split the same way.

A public remote has no confidentiality benefit. Anyone who can read the chain can read the file bytes. The cost above is what you pay for that.

A forge is a separate no. A pull request, an issue, and a CI status are one note each. A 12 KB log was four notes. Together, on the private object mailbox, that was 7 notes, 7,924 µALGO, one round. Status on the mailbox is cheap. A megabyte of log costs the same as a megabyte of blob, and the organization is not one repository.

## What the chain holds

Two write models, same mailbox, same fee rule.

Objects. Each reachable git object is stored once, as the canonical `type size\\0` bytes plus the payload. A later push skips any object id the mailbox already has. Refs are their own notes. The last note for a ref name, in round then intra-round order, wins.

Deltas. Commits, trees, and tags stay full objects. A changed blob is a Git binary delta of the file bytes against the previous blob of that path (first parent, or the root diff for a root commit), and only when the delta is smaller than the canonical object. Clone reconstructs the blob and checks the git object id. The delta is a storage encoding, not a second hash.

Framing is not a cipher. An `ALGT` frame is 51 bytes plus payload: magic, version, kind, flags, object id, delta base, chunk index, chunk count. Public notes are the frame, so a chunk holds 4,045 payload bytes. Private notes are `seal_group_message` of that frame. AlgoChat's group plaintext max is 4,026 bytes, so a private chunk holds 3,975 payload bytes. The `0x07` envelope adds a 54-byte header and a 16-byte tag.

The private data path is one group mailbox and `0x07` only. Session setup is the real AlgoChat sequence at PQ level 3: a `0x04` handshake (2,366 bytes), one `0x05` session proof (`ALGit session ready`), a public `0x03` create, a public `0x03` add-member in a later round, and a `0x06` action-5 key delivery (227 bytes). Everyday `0x01` and the extra lock `0x02` are not used. File bytes, object ids, and ref names sit inside the `0x07` ciphertext. Clone reads every payment to the mailbox, opens the notes it can open, and ignores the rest. There is no separate have-negotiation, because a private object id is not visible until the note opens.

## What stays public

AlgoChat is explicit about this in PROTOCOL.md section 11.3, and the LocalNet notes match it. A chain observer sees the sender, the receiver, the round time, the fee, and the note size. A `0x07` note also leaves the clear header in PROTOCOL.md section 5.8: version `0x02`, protocol `0x07`, the 32-byte group id, epoch, counter, and nonce. `0x03` records publish the room name, policy, owner, admins, and members. `0x04` publishes the X25519 keys and the ML-KEM ciphertext. Signed key announcements publish the encapsulation key. File bytes are secret only in the private model, and only from someone who cannot open `0x04`, `0x05`, `0x06`, and `0x07`.

On the private object mailbox the outsider's X25519 key was rejected for the handshake, for `0x05`, and for `0x06` (`Handshake is for a different X25519 key`). A random group key failed with `Group message authentication failed`. A second `0x07` that reused counter 0 was rejected by the opener (`repeated group counter`); the import read-back reported that one rejection and still assembled every git frame. The private marker `ALGit private marker 7e1c9a4b` did not occur in any raw note of the import or the edits. The same marker on the public mailbox occurred in the one-line push.

## Fee rule, checked on LocalNet

PROTOCOL.md section 10.3, Ed25519, `minFee` 1000:

```
over      = max(0, noteBytes - 1024)
surcharge = (over * minFee + 9999) / 10000
fee       = minFee + surcharge
```

A full 4,096-byte note is 1,308 µALGO. The installed SDK does not apply this. `py-algorand-sdk` 2.12.0 will build a note longer than 1,024 bytes, and its `NOTE_MAX_LENGTH` constant is now documented as the fee-free allowance, not a hard cap. The previous release, 2.11.1, still raises `WrongNoteLength` above 1,024 bytes inside `Transaction.as_note`. This sandbox advertises a per-byte fee of 0, so a transaction left to the SDK's size estimate pays 1,000 µALGO and consensus rejects it. The harness sets `flat_fee` to the formula above.

The probe, from fresh accounts, rounds 150333–150335:

| Note | Fee charged | Round | Transaction |
| --- | ---: | ---: | --- |
| 4,096 bytes | 1,308 | 150333 | `TTLZXNT4KLINJ66HW757KJ4IXACRHAZQKPGFXCJEUOM3CWG65PGQ` |
| 1,024 bytes | 1,000 | 150334 | `2KBSYNC2E42X7FPENMBSFNPOXRQS6U5RTGX2A7IF5L7YBHRUTJ2A` |
| 1,025 bytes | 1,001 | 150335 | `RHJ66Z5RLVTF7XBYD7NS5WFIY6I5N2WZL3CAER4GXQPORIPNVNTQ` |

The 4,096-byte note was read back out of block 150333 and matched. The same 4,096-byte note submitted at 1,000 µALGO was rejected: `TransactionPool.Remember: txgroup with 1mA fees is less than 1.308mA (usage=1.307200 * base=1mA)`. Consensus on this sandbox does apply the surcharge. Falcon-1024 is three times the scheme minimum and was not the scheme under test.

## CorvidLabs, recounted

`gh repo list CorvidLabs` during the run, `diskUsage` in KB as GitHub returns it. The snapshot of 100 repositories and about 2.47 GB is behind this.

| | |
| --- | ---: |
| Repositories | 221 |
| Private / public | 97 / 124 |
| Archived | 17 |
| Forks | 2 |
| `diskUsage` sum | 5,734,733 KB (5.47 GiB) |

Named repositories, KB and the MiB figure that matches KB/1024:

| Repository | KB | MiB | Visibility in the census |
| --- | ---: | ---: | --- |
| jay.corvid.algo | 1,845,824 | 1,803 | private |
| corvid-dress | 777,236 | 759 | private |
| site | 538,649 | 526 | private |
| peck | 400,301 | 391 | private |
| Roost | 298,774 | 292 | private |
| 3md | 267,135 | 261 | public |
| Talon | 259,399 | 253 | private |
| algochat | 2,433 | 2.38 | public |

Scaling the measured `site` rate across that sum is arithmetic, not another chain run. `site` cost 290.717 ALGO for 538,649 KB, which is 539.7 µALGO per GitHub KB. Applied to 5,734,733 KB that is about 3,095 ALGO. That floor prices every repository as a full `site` history, images included. `algochat` cost 3,763 µALGO per GitHub KB, seven times the `site` rate, because small trees and commits each pay a whole 1,000 µALGO note. A CID split lowers the rate for an image-heavy history and does not lower it for a source repository. `jay.corvid.algo` alone, at the full-blob `site` rate, is about 1,000 ALGO.

## algochat on three mailboxes

Each run had its own mailbox. History is `origin` plus tags, not the local branches. The pack of that rev list is 2,667,968 bytes. Canonical objects are 18,972,367 bytes (2,485 blobs, 1,604 trees, 206 commits, 3 tags).

Private object mailbox `VSHKGND3IHH36SRHXBNA5FMRUP5XKUL4AIHU6RCFWRZ6HGWZO3C5RF7QHA`, writer `OJTKNOPLWFGWTNGRU77KTDMDD2LUYD6BV2O5ADEJ3WVK6I5ETM2JSQUSMA`. Room setup was 12 notes, 12,181 µALGO, rounds 151813–151824, from `4TCWRWXGUFIAGOEHC7FPKRSFJJW23GZ6AWZLNHAJP3L3TWBMV3QQ` through `22ETBCX4BLHKTAUOJXWRU23PTLF4RMQ3QGNHMSZR226UHR5U74SA`. The import was rounds 151825–152336.

| | Objects, private | Deltas, private | Objects, public |
| --- | --- | --- | --- |
| Mailbox | `VSHKGND3…RF7QHA` | `LUVIMI7IQ476MXW53QEISDZQGHMWD7F3POHIA6ROO33LRNU3QE7GAKHV34` | `URH4NIN63PTPZA27RJHAHBZIYX6EXXBS5CSXRSB7L5SLWPYTZFY4YF35OE` |
| Notes | 7,944 | 6,320 | 7,875 |
| Note bytes | 19,934,402 | 11,900,056 | 19,374,803 |
| Fee | 9,256,939 µALGO | 7,044,568 µALGO | 9,156,482 µALGO |
| Push | 38.019 s | 30.323 s | 32.519 s |
| Read back | 32.445 s | 14.246 s | 9.874 s |
| Rounds | 151825–152336 (497) | 152395–152837 (395) | 152854–153399 (493) |
| First tx | `MGDK4XRSTEIANKFNZKJKHG2LN35C7I2F43Q7DYRDXCPWJWVIRGFA` | `7GWLE262HVYUKL6T43R3IXRU7XLPMMRJL4ZRNPOOTSU47HOBKLHA` | `N2UGM5LJHR6WFPCGHQRVEF3IYZLTPHHLLOYQBTN7GKEQC22WKZMA` |
| Last tx | `K77W2OKEX63XWFE6ASD4PASTNWVESSMAESUZEHRXOZCZEV24UKJQ` | `3GTW7FOCEXTSBL4YICUHNSGPZPCZLGWVN7MZSYPBYF7ZCF2OXGXQ` | `WF44YF2S6FM2HXCM6PEIONP3UG5UBZI7GN56BAQUP4USWRLAFLVQ` |
| Objects rebuilt | 4,298 | 4,298 | 4,298 |
| `git fsck --full` | 0 | 0 | 0 |

The first private import note begins with `0x02 0x07` and the group id. The first public note begins with `ALGT`. Read-back fetched 7,946 `0x07` notes for the private object import (the ping and the rejected duplicate sit in that count) and 7,875 `ALGT` notes for the public import, matching the payments. Groups of 16 payments landed in one round. Sustained write rate on these runs was about 210 to 370 notes per second.

Public deltas were not given a fourth mailbox. Their fee, from the same pieces with the 70-byte envelope removed, is 6,284 notes and 6,989,985 µALGO. The private delta run is the wall-time measurement for that encoding.

### Edits, then a push of what is already there

The work clone added three commits on top of `origin/main`: one marker line in `README.md`, a new 61,440-byte random file, then a replacement of that file with different random bytes.

| Edit | Model | Notes | Fee µALGO | Payload bytes | Seconds | Round |
| --- | --- | ---: | ---: | ---: | ---: | --- |
| One line | private objects | 6 | 6,663 | 10,344 | 0.046 | 152359 |
| One line | private deltas | 4 | 4,047 | 1,664 | 0.035 | 152842 |
| One line | public objects | 6 | 6,656 | 10,343 | 0.029 | 153405 |
| Add 60 KiB | private objects | 19 | 23,765 | 63,119 | 0.133 | 152360–152361 |
| Add 60 KiB | private deltas | 19 | 23,765 | 63,119 | 0.075 | 152843–152844 |
| Add 60 KiB | public objects | 19 | 23,665 | 63,119 | 0.115 | 153406–153407 |
| Replace 60 KiB | private objects | 19 | 23,765 | 63,125 | 0.205 | 152363–152364 |
| Replace 60 KiB | private deltas | 19 | 23,765 | 63,125 | 0.090 | 152845–152846 |
| Replace 60 KiB | public objects | 19 | 23,665 | 63,125 | 0.064 | 153408–153409 |

The one-line delta is one blob delta plus two full objects (the new tree and commit) and the ref. The 60 KiB add has no previous blob, so both models store it whole. The 60 KiB replace is two unrelated random strings. The delta was larger than the object, so the delta model stored the new blob whole too. Deltas pay off on text history and on a one-line edit. They do not pay off on a binary replace.

Each model then pushed `origin/main` again, which was already on the mailbox. Object pieces in that plan: 0. One ref note, 1,000 µALGO. Private note 136 bytes (`PZYRSEJIWW7O7E4MIA6PTSS7TLJM2EAOYLQONDDBDTNY2C6OIGZQ`, round 152365, and `OEBTR5C6JN5B6KXUEP3IVVHC2Y6CL4BEFU75Y5FQQFQBMOBXOFBQ`, round 152848). Public note 66 bytes (`DQIU3OGWTDFDBEHCQNNQWMCPSQ5HNCB7DVYVT7WUWPDVBV4E54HQ`, round 153410). The 70-byte gap is the `0x07` header and tag.

Every edit was opened back off the block and reassembled. Full objects matched their git object id. Deltas were applied to `git cat-file blob` of the base and the reconstructed blob matched its object id. The ref payload was `refs/heads/measure`.

## site, public objects, on chain

Offline plans for both models and both visibilities, then one chain run: public objects, no group seal. Writer funded with 800 ALGO. Fee paid was 290.717 ALGO.

| Plan | Notes | Fee | Payload |
| --- | ---: | ---: | ---: |
| Objects, public (chained) | 225,869 | 290,717,152 µALGO | 862,108,466 |
| Objects, private | 229,513 | 295,554,039 µALGO | 862,108,466 |
| Deltas, public | 188,354 | 241,300,903 µALGO | 704,530,606 |
| Deltas, private | 191,325 | 245,244,901 µALGO | 704,530,606 |

Chain result, mailbox `3SGWVEFQBYI6N4JSYXCCWRHLOX6OYRR6O4XZRFENEW6GFIJGYW3T4JZSGQ`, writer `SVOVBBNB7SQQYUE7FI3M2YGFSHM46A2GFNQX6UBTGWHAHSPNAT4CCX44ZI`:

- 225,869 notes, 873,627,785 note bytes, 290,717,152 µALGO
- 606.517 seconds to push, about 370 notes per second over the whole send
- rounds 153620–167836, 14,117 rounds
- first `ELYI4CKFAET3HUP2PMEAUO5H3IPBLEBZ3OJ6KF5Y4Z7Y4U3DQNZQ`
- last `OTGTORHAEAS7YPAZBNOPWGHK5P7PWCPRI34WWPIACQMHQVARUBNA`
- read-back 87.941 seconds, 225,869 `ALGT` notes fetched, equal to the payments
- 9,174 single-chunk objects checked by SHA-1 during the scan
- `git fsck --full` exit 0, 20,709 loose objects, 23 refs, `main` at `a658383d1f968daced4eba86a0ee22d7950756b3`

Deltas would have saved about 49 ALGO on this repository and were not pushed. The object import is the heavier of the two, which is the one that answers "can you land it."

## If the heavy files were CIDs

The import above stores every blob. On the same origin-plus-tags set, raster images are 9,808 blobs, 483.6 MiB, and 169.060 ALGO, 58% of the 290.694 ALGO of object fees. 9,807 of those blobs are reachable from `origin/main`. `public/nevermore` alone is 127.157 ALGO. The largest PNG prefixes match PNG. None of the raster blobs is a Git LFS pointer.

A 72-byte `ipfs://` pointer is one note and 1,000 µALGO. Tree and commit sizes stay put, because a tree entry holds a 20-byte object id either way. Replacing a blob still rewrites history, since the new blob has a new id. The figures below are that rewritten set. They were not committed and not pushed. IPFS pinning is not in the fee.

| What stays as git blobs | Private ALGO | Public ALGO | Public notes |
| --- | ---: | ---: | ---: |
| Everything, as stored | 295.554 | 290.717 | 225,869 |
| Everything except raster images | 133.442 | 131.465 | 104,856 |
| Source, published JSON, other published files, SVG, trees, commits | 53.852 | 53.248 | 45,197 |
| Source, trees, and commits | 40.733 | 40.324 | 35,366 |
| Source code, docs, trees, and commits | 30.548 | 30.330 | 27,786 |

The public column is the fee rule that matched the chain payment to the microALGO. The private column is the offline plan method. Inside the 22.515 ALGO source bucket, code under `src/` excluding `src/data` is 9.005 ALGO, specsync records are 6.218, and the catalogues are 5.005. October 2026 added 169.566 ALGO of new objects, 136.901 of that in images.

Per-byte prices are close: about 0.35 ALGO per MiB of image and 0.37 per MiB of source. The images cost what they cost because they are 484 MiB. 239 image blobs of 1 MiB or larger are 102.362 ALGO. 4,827 image blobs under 8 KiB are 9.046 ALGO. The month series, directory breakdown, and confidence table are in [site-onchain-cost.html](site-onchain-cost.html).

## Pull requests, issues, and CI

Feasible as more notes on the same mailbox. Not the first product. Posted on the private object mailbox after the dedup ref, round 152366, 7 notes, 13,360 note bytes, 7,924 µALGO:

| Note | Transaction |
| --- | --- |
| pull request | `Y7MVEZYOI2CFHEWUKLDLCIK7XRDMVQ2C6W3C5P324UFDZOEEOVUA` |
| issue | `77YUZ2YTZBXULGSFDDIWEAJOTGYUSSLF47HOZOX22TG62424C2CQ` |
| CI status | `E4GCONWTIT7KAZBI4FWHTAFSD7HLS27P63VO5I7FJ4HIEWU3HCFQ` |
| CI log, 12,000 bytes, four chunks | `JV6T4TISPQOO647C3T56IPYMP2WCGNPGQVCUTOSIPRZJ6KTJPWXQ` … `EGYO27P56QLYOXKTCEIX7AKWAUTLGHGXPSLM3M2AADQT4PB2RQNQ` |

A status row is the cost of a tiny note, 1,000 µALGO plus a few hundred if the JSON passes 1,024 bytes. Comments are the same shape. A log is a blob: the 12 KB sample needed four notes, and a 1 MB log needs on the order of 250 notes and about 0.3 ALGO. Keep status on the mailbox. Keep logs off it, or accept blob prices.

Nothing in that design runs a job, renders a diff, or enforces review. Membership is the `0x03` roster, which is public. Discovery across the organization is not a mailbox.

## A pack would be cheaper, and still would not carry site

`git pack-objects` of the `algochat` rev list was 2,667,968 bytes. If those bytes were split into 4,096-byte notes and paid with the same fee rule, that is 651 full notes and a 1,472-byte tail: 852,553 µALGO, about 0.85 ALGO. The object import cost 9.16 ALGO. The pack bound is arithmetic on the measured pack size. It was not pushed. Per-object dedup, which the second push measured at one 1,000 µALGO ref, is the property you give up if the remote only stores packs.

The same arithmetic on `site`'s GitHub `diskUsage` (551,576,576 bytes) is 176.14 ALGO. The measured object import was 290.72 ALGO because inflated objects are larger than GitHub's packed disk. A pack encoding narrows that gap. It leaves a 526 MiB repository at well over 100 ALGO for one publish. That pack bound includes the images and the peck binaries. It is not a source-only figure.

## Where this leaves the product

The numbers that fit a product are a private repository on the order of `algochat`: under 10 ALGO and under a minute for a full history, and 1,000 µALGO for a push that only moves a ref. Store objects, and store a blob delta when the delta is smaller. The one-line edit is the case that would justify the second encoding. The 60 KiB replace is the case that shows it is not magic. We are not building that remote.

`site` at 291 ALGO and ten minutes is a LocalNet existence proof, funded here with 800 ALGO so the fee could not be the reason it failed. It succeeded. As stored, it is the wrong remote for that repository. Putting the images on IPFS leaves 133.442 ALGO private. Keeping the source and storing every other blob as a CID leaves 40.733 ALGO private, or 30.548 if specsync snapshots and the `src/data` catalogues are CIDs too. That is still three to four times `algochat`, so it is not the remote to build first. A public mailbox is the same design with the ciphertext removed, and the measurement says not to offer it. GitHub remains the forge. The mailbox can hold a pull request, an issue, and a CI status beside the refs. It should not hold the logs, and it should not hold the organization.
