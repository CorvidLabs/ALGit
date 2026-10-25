"""Push, clone, pin, and serve one git repository."""

from __future__ import annotations

import base64
import hashlib
import json
import os
import shutil
import subprocess
import threading
import urllib.error
import urllib.request
import zlib
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

__all__ = [
    "fee_for_note",
    "plan_repository",
    "materialize_frames",
    "quote_push",
    "push_localnet",
    "clone_mailbox",
    "pin_heavy_blobs",
    "serve",
    "main",
]

MAGIC = b"ALGT"
VERSION = 1
HEADER = 51
PUBLIC_CHUNK = 4096 - HEADER
HEAVY = 262_144
KIND_OBJECT = 1
KIND_REF = 3
ZERO = b"\x00" * 20
TOKEN = "a" * 64
LOCAL_ALGOD = "http://127.0.0.1:4001"
LOCAL_KMD = "http://127.0.0.1:4002"
LOCAL_INDEXER = "http://127.0.0.1:8980"
MAINNET_ALGOD = "https://mainnet-api.algonode.cloud"
PIN_ENDPOINT = "https://api.pinata.cloud/pinning/pinFileToIPFS"

USAGE = """algit push [--network localnet|mainnet] [--yes] [--repo PATH]
algit clone <mailbox> [--into PATH] [--network localnet]
algit serve [--repo PATH] [--port 4711]

push spends on LocalNet only after --yes, and only after it prints the fee.
push --network mainnet prints the fee and spends nothing.
A blob over 256 KiB is pinned with PINATA_JWT and PINATA_GATEWAY first.
The page listens on 127.0.0.1.
"""


def fee_for_note(note_len: int, min_fee: int = 1000) -> int:
    """MicroALGO for one note. PROTOCOL.md section 10.3, Ed25519."""
    if note_len < 0 or note_len > 4096:
        raise ValueError(f"note length {note_len} is not legal")
    over = max(0, note_len - 1024)
    surcharge = (over * min_fee + 9999) // 10000
    return min_fee + surcharge


def quote_push(repo: str, min_fee: int = 1000, env: dict | None = None, endpoint: str | None = None) -> dict:
    """Price a repository. This does not submit a transaction."""
    plan = plan_repository(repo, env=env, endpoint=endpoint)
    notes = plan.notes()
    micro = sum(fee_for_note(len(note), min_fee) for note in notes)
    return {
        "notes": len(notes),
        "microalgo": micro,
        "algo": micro / 1_000_000,
        "objects": plan.object_count,
        "pinned": plan.pinned,
        "submitted": 0,
        "head": plan.head,
    }


def plan_repository(repo: str, env: dict | None = None, endpoint: str | None = None):
    """Canonical objects and branch refs. Heavy blobs are pinned, then stored as pointers."""
    env = os.environ if env is None else env
    objects = _load_objects(repo, ["--branches", "--tags"])
    if not objects:
        raise RuntimeError(f"{repo} has no commits")
    stored = dict(objects)
    mapping: dict[str, str] = {}
    heavy = [(oid, content) for oid, (kind, content) in objects.items() if kind == "blob" and len(content) > HEAVY]
    pinned = []
    if heavy:
        pinned = pin_heavy_blobs([(oid, content) for oid, content in heavy], env, endpoint=endpoint)
        by_oid = {item["name"]: item for item in pinned}
        for oid, _content in heavy:
            pointer = f"ipfs://{by_oid[oid]['cid']}\n".encode()
            new_oid = hashlib.sha1(_canonical("blob", pointer)).hexdigest()
            mapping[oid] = new_oid
            stored[new_oid] = ("blob", pointer)
    _rewrite(objects, stored, mapping)
    tips = []
    pieces = []
    for name, oid in _local_refs(repo):
        target = _resolve(oid, mapping)
        tips.append(target)
        pieces.append(_Piece(KIND_REF, target, name.encode()))
    reachable = _reachable(tips, stored)
    for oid in sorted(reachable):
        kind, content = stored[oid]
        pieces.append(_Piece(KIND_OBJECT, oid, _canonical(kind, content)))
    head = _git(repo, "rev-parse", "HEAD").decode().strip()
    return _Plan(pieces, len(reachable), pinned, _resolve(head, mapping))


def materialize_frames(frames: list[dict], out_dir: str) -> dict:
    """Rebuild a bare git directory from ALGT frames and run git fsck."""
    objects: dict[bytes, bytes] = {}
    ref_frames = []
    buckets: dict[bytes, list[dict]] = {}
    for item in frames:
        if item["kind"] == KIND_REF:
            ref_frames.append(item)
            continue
        buckets.setdefault(item["oid"], []).append(item)
    for oid, chunks in buckets.items():
        chunks.sort(key=lambda item: item["index"])
        count = chunks[0]["count"]
        if [item["index"] for item in chunks] != list(range(count)):
            raise RuntimeError(f"missing chunk for {oid.hex()}")
        payload = b"".join(item["payload"] for item in chunks)
        if hashlib.sha1(payload).digest() != oid:
            raise RuntimeError(f"object {oid.hex()} failed sha1")
        objects[oid] = payload
    git_dir = Path(out_dir) / "repo.git"
    if git_dir.exists():
        shutil.rmtree(git_dir)
    subprocess.check_call(["git", "init", "--bare", "-q", str(git_dir)])
    for oid, raw in objects.items():
        digest = oid.hex()
        path = git_dir / "objects" / digest[:2] / digest[2:]
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(zlib.compress(raw))
    latest: dict[str, str] = {}
    for item in ref_frames:
        if item["count"] != 1 or item["index"] != 0:
            raise RuntimeError("a ref spanned more than one note")
        latest[item["payload"].decode()] = item["oid"].hex()
    for name, oid in latest.items():
        subprocess.check_call(["git", "--git-dir", str(git_dir), "update-ref", name, oid])
    fsck = subprocess.run(
        ["git", "--git-dir", str(git_dir), "fsck", "--full"],
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
    )
    return {
        "objects": len(objects),
        "refs": latest,
        "fsck_code": fsck.returncode,
        "fsck": fsck.stdout.strip(),
        "git_dir": str(git_dir),
    }


def pin_heavy_blobs(blobs: list[tuple[str, bytes]], env: dict, endpoint: str | None = None) -> list[dict]:
    """Upload blobs over 256 KiB. `blobs` are `(name, content)` pairs."""
    jwt = (env.get("PINATA_JWT") or "").strip()
    gateway = (env.get("PINATA_GATEWAY") or "").strip()
    if not jwt or not gateway:
        raise RuntimeError("Set PINATA_JWT and PINATA_GATEWAY. A blob is over 256 KiB.")
    host = gateway.replace("https://", "").replace("http://", "").strip("/")
    pinned = []
    for name, content in blobs:
        if len(content) <= HEAVY:
            continue
        cid = _post_pin(content, name, jwt, endpoint or PIN_ENDPOINT)
        pinned.append(
            {
                "name": name,
                "cid": cid,
                "bytes": len(content),
                "url": f"https://{host}/ipfs/{cid}",
            }
        )
    return pinned


def push_localnet(repo: str, state_dir: str | None = None, env: dict | None = None, endpoint: str | None = None) -> dict:
    """Print the fee, then pay the notes to a new LocalNet mailbox."""
    quote = quote_push(repo, env=env, endpoint=endpoint)
    print(
        f"{quote['notes']} notes, {quote['microalgo']} microALGO ({quote['algo']:.6f} ALGO)",
        flush=True,
    )
    from algosdk import account, transaction
    from algosdk.kmd import KMDClient
    from algosdk.v2client.algod import AlgodClient

    algod = AlgodClient(TOKEN, LOCAL_ALGOD)
    kmd = KMDClient(TOKEN, LOCAL_KMD)
    dispenser_key, dispenser = _dispenser(kmd)
    writer_key, writer = account.generate_account()
    mailbox_key, mailbox = account.generate_account()
    fund = max(quote["microalgo"] + 500_000, 1_000_000)
    _pay(algod, dispenser_key, dispenser, [(mailbox, 300_000, b""), (writer, fund, b"")])
    plan = plan_repository(repo, env=env, endpoint=endpoint)
    notes = plan.notes()
    sent = _pay(
        algod,
        writer_key,
        writer,
        [(mailbox, 0, note) for note in notes],
    )
    rounds = sorted({row["round"] for row in sent})
    _wait_indexer(rounds[-1] if rounds else 0)
    state = {
        "network": "localnet",
        "mailbox": mailbox,
        "writer": writer,
        "head": plan.head,
        "notes": len(notes),
        "microalgo": quote["microalgo"],
        "rounds": rounds,
        "pinned": quote["pinned"],
    }
    destination = Path(state_dir) if state_dir else Path(repo) / ".algit"
    destination.mkdir(parents=True, exist_ok=True)
    receipt = destination / "remote.json"
    receipt.write_text(json.dumps(state, indent=2) + "\n")
    key_path = destination / "writer.json"
    key_path.write_text(json.dumps({"address": writer, "private_key": writer_key}) + "\n")
    os.chmod(key_path, 0o600)
    state["receipt"] = str(receipt)
    return state


def clone_mailbox(mailbox: str, into: str, indexer: str = LOCAL_INDEXER) -> dict:
    """Read a mailbox from the indexer and materialize it."""
    frames = _frames_from_indexer(mailbox, indexer)
    if not frames:
        raise RuntimeError(f"no ALGT notes for {mailbox}")
    built = materialize_frames(frames, into)
    work = Path(into) / "work"
    if work.exists():
        shutil.rmtree(work)
    built["branch"] = _checkout_work(built["git_dir"], built["refs"], str(work))
    built["work"] = str(work)
    built["mailbox"] = mailbox
    return built


def serve(repo: str, host: str = "127.0.0.1", port: int = 4711, mailbox: str = "", network: str = "localnet", background: bool = False):
    """Serve the local page for a cloned repository. Binds to 127.0.0.1."""
    if host != "127.0.0.1":
        raise RuntimeError("the page listens on 127.0.0.1")
    root = Path(repo).resolve()
    if not (root / ".git").exists() and not (root / "HEAD").exists():
        raise RuntimeError(f"{repo} is not a git repository")
    receipt = {"mailbox": mailbox, "network": network, "repo": root.name}

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self) -> None:  # noqa: N802
            parsed = urlparse(self.path)
            if parsed.path == "/":
                self._send(200, "text/html; charset=utf-8", _page(receipt).encode())
                return
            if parsed.path == "/api/overview":
                self._send(200, "application/json", json.dumps(_overview(root, receipt)).encode())
                return
            query = parse_qs(parsed.query)
            if parsed.path == "/api/file":
                try:
                    rel = _safe_path(query.get("path", [""])[0])
                    body = _git(str(root), "show", f"HEAD:{rel}")
                except (ValueError, RuntimeError) as exc:
                    self._send(400, "text/plain; charset=utf-8", str(exc).encode())
                    return
                self._send(200, "application/octet-stream", body)
                return
            if parsed.path == "/api/diff":
                rev = query.get("rev", ["HEAD"])[0]
                if not _hexish(rev):
                    self._send(400, "text/plain; charset=utf-8", b"bad revision")
                    return
                try:
                    body = _git(str(root), "show", "--format=fuller", "--unified=3", rev)
                except RuntimeError as exc:
                    self._send(400, "text/plain; charset=utf-8", str(exc).encode())
                    return
                self._send(200, "text/plain; charset=utf-8", body)
                return
            self._send(404, "text/plain; charset=utf-8", b"not found")

        def _send(self, status: int, content_type: str, body: bytes) -> None:
            self.send_response(status)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, fmt: str, *args) -> None:
            return

    httpd = ThreadingHTTPServer((host, port), Handler)
    if background:
        thread = threading.Thread(target=httpd.serve_forever, daemon=True)
        thread.start()
        return httpd
    print(f"http://{host}:{httpd.server_address[1]}/", flush=True)
    httpd.serve_forever()
    return httpd


def main(argv: list[str] | None = None) -> int:
    """Command line entry for push, clone, and serve."""
    args = list(_argv() if argv is None else argv)
    if not args or args[0] in {"-h", "--help"}:
        print(USAGE)
        return 0
    command, rest = args[0], args[1:]
    try:
        if command == "push":
            return _cmd_push(rest)
        if command == "clone":
            return _cmd_clone(rest)
        if command == "serve":
            return _cmd_serve(rest)
    except Exception as exc:  # noqa: BLE001
        print(exc, flush=True)
        return 1
    print(USAGE)
    return 2


def _argv() -> list[str]:
    import sys

    return sys.argv[1:]


def _cmd_push(args: list[str]) -> int:
    network = _option(args, "--network", "localnet")
    repo = _option(args, "--repo", ".")
    if network == "mainnet":
        quote = quote_push(repo, min_fee=_mainnet_min_fee())
        print(
            f"MainNet quote: {quote['notes']} notes, {quote['microalgo']} microALGO ({quote['algo']:.6f} ALGO). Nothing was sent.",
            flush=True,
        )
        return 0
    if network != "localnet":
        raise RuntimeError("network is localnet or mainnet")
    if "--yes" not in args:
        quote = quote_push(repo)
        print(
            f"LocalNet quote: {quote['notes']} notes, {quote['microalgo']} microALGO ({quote['algo']:.6f} ALGO).",
            flush=True,
        )
        print("Pass --yes to pay this on LocalNet.", flush=True)
        return 0
    state = push_localnet(repo)
    print(f"mailbox {state['mailbox']}", flush=True)
    print(f"receipt {state['receipt']}", flush=True)
    return 0


def _cmd_clone(args: list[str]) -> int:
    positional = [arg for arg in args if not arg.startswith("--") and arg != _option(args, "--into", "")]
    # `--into` consumes its value via _option; drop that value too.
    into = _option(args, "--into", "")
    mailbox = ""
    skip_next = False
    for arg in args:
        if skip_next:
            skip_next = False
            continue
        if arg in {"--into", "--network"}:
            skip_next = True
            continue
        if arg.startswith("--"):
            continue
        mailbox = arg
        break
    if not mailbox:
        raise RuntimeError("name the mailbox")
    destination = into or str(Path(".algit") / mailbox[:8])
    built = clone_mailbox(mailbox, destination)
    if built["fsck_code"] != 0:
        raise RuntimeError(built["fsck"] or "git fsck failed")
    print(f"fsck clean, {built['objects']} objects, work {built['work']}", flush=True)
    return 0


def _cmd_serve(args: list[str]) -> int:
    repo = _option(args, "--repo", ".")
    port = int(_option(args, "--port", "4711"))
    receipt_path = Path(repo).parent / ".algit" / "remote.json"
    if not receipt_path.exists():
        receipt_path = Path(".algit") / "remote.json"
    mailbox = ""
    network = "localnet"
    if receipt_path.exists():
        saved = json.loads(receipt_path.read_text())
        mailbox = saved.get("mailbox", "")
        network = saved.get("network", "localnet")
    serve(repo, port=port, mailbox=mailbox, network=network)
    return 0


def _option(args: list[str], name: str, default: str) -> str:
    if name not in args:
        return default
    index = args.index(name)
    if index + 1 >= len(args):
        raise RuntimeError(f"{name} needs a value")
    return args[index + 1]


def _mainnet_min_fee() -> int:
    try:
        with urllib.request.urlopen(MAINNET_ALGOD + "/v2/transactions/params", timeout=5) as response:
            data = json.loads(response.read().decode())
        return int(data.get("min-fee") or 1000)
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError, ValueError):
        return 1000


def _canonical(kind: str, content: bytes) -> bytes:
    return f"{kind} {len(content)}\0".encode() + content


class _Piece:
    def __init__(self, kind: int, oid: str, payload: bytes) -> None:
        self.kind = kind
        self.oid = oid
        self.payload = payload


class _Plan:
    def __init__(self, pieces: list[_Piece], object_count: int, pinned: list[dict], head: str) -> None:
        self.pieces = pieces
        self.object_count = object_count
        self.pinned = pinned
        self.head = head

    def notes(self) -> list[bytes]:
        notes: list[bytes] = []
        for piece in self.pieces:
            oid = bytes.fromhex(piece.oid) if piece.kind == KIND_OBJECT or _hexish(piece.oid) else ZERO
            if len(oid) != 20:
                oid = ZERO
            payload = piece.payload
            width = PUBLIC_CHUNK
            parts = [payload[index : index + width] for index in range(0, max(len(payload), 1), width)] or [b""]
            count = len(parts)
            for index, part in enumerate(parts):
                notes.append(_frame(piece.kind, oid, index, count, part))
        return notes


def _frame(kind: int, oid: bytes, index: int, count: int, payload: bytes) -> bytes:
    if len(oid) != 20:
        raise ValueError("sha1 oids are 20 bytes")
    if len(_frame_bytes(kind, oid, index, count, payload)) > 4096:
        raise ValueError("note is longer than 4096 bytes")
    return _frame_bytes(kind, oid, index, count, payload)


def _frame_bytes(kind: int, oid: bytes, index: int, count: int, payload: bytes) -> bytes:
    return MAGIC + bytes([VERSION, kind, 0]) + oid + ZERO + index.to_bytes(2, "big") + count.to_bytes(2, "big") + payload


def _parse_frame(data: bytes) -> dict:
    if len(data) < HEADER or data[:4] != MAGIC or data[4] != VERSION:
        raise ValueError("not an ALGT frame")
    return {
        "kind": data[5],
        "oid": data[7:27],
        "index": int.from_bytes(data[47:49], "big"),
        "count": int.from_bytes(data[49:51], "big"),
        "payload": data[HEADER:],
    }


def _git(repo: str, *args: str) -> bytes:
    result = subprocess.run(
        ["git", "-C", repo, *args],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )
    if result.returncode != 0:
        raise RuntimeError(result.stderr.decode() or f"git {' '.join(args)} failed")
    return result.stdout


def _load_objects(repo: str, rev_args: list[str]) -> dict[str, tuple[str, bytes]]:
    listed = _git(repo, "rev-list", "--objects", *rev_args)
    oids = []
    seen = set()
    for line in listed.splitlines():
        oid = line.split()[0].decode()
        if oid not in seen:
            seen.add(oid)
            oids.append(oid)
    if not oids:
        return {}
    proc = subprocess.Popen(
        ["git", "-C", repo, "cat-file", "--batch"],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
    )
    assert proc.stdin and proc.stdout
    found: dict[str, tuple[str, bytes]] = {}

    def read_exact(count: int) -> bytes:
        buf = b""
        while len(buf) < count:
            chunk = proc.stdout.read(count - len(buf))
            if not chunk:
                raise EOFError("cat-file ended early")
            buf += chunk
        return buf

    for oid in oids:
        proc.stdin.write(oid.encode() + b"\n")
        proc.stdin.flush()
        header = proc.stdout.readline()
        if not header or header.endswith(b" missing\n"):
            continue
        got, kind, size_text = header.split()
        content = read_exact(int(size_text))
        if read_exact(1) != b"\n":
            raise RuntimeError("cat-file framing")
        found[got.decode()] = (kind.decode(), content)
    proc.stdin.close()
    proc.stdout.close()
    proc.wait()
    return found


def _local_refs(repo: str) -> list[tuple[str, str]]:
    refs = []
    listed = _git(repo, "for-each-ref", "--format=%(objectname) %(refname)", "refs/heads", "refs/tags")
    for line in listed.splitlines():
        oid, name = line.decode().split(" ", 1)
        refs.append((name, oid))
    return refs


def _resolve(oid: str, mapping: dict[str, str]) -> str:
    seen = set()
    while oid in mapping and oid not in seen:
        seen.add(oid)
        oid = mapping[oid]
    return oid


def _rewrite(objects: dict[str, tuple[str, bytes]], stored: dict[str, tuple[str, bytes]], mapping: dict[str, str]) -> None:
    progress = True
    while progress:
        progress = False
        for oid, (kind, content) in objects.items():
            if kind == "tree":
                body, dirty = _rewrite_tree(content, mapping)
            elif kind == "commit":
                body, dirty = _rewrite_text(content, mapping, (b"tree ", b"parent "))
            elif kind == "tag":
                body, dirty = _rewrite_text(content, mapping, (b"object ",))
            else:
                continue
            if not dirty:
                continue
            new_oid = hashlib.sha1(_canonical(kind, body)).hexdigest()
            if mapping.get(oid) != new_oid:
                mapping[oid] = new_oid
                stored[new_oid] = (kind, body)
                progress = True


def _rewrite_tree(content: bytes, mapping: dict[str, str]) -> tuple[bytes, bool]:
    entries = _parse_tree(content)
    rebuilt = []
    dirty = False
    for mode, name, raw in entries:
        mapped = _resolve(raw.hex(), mapping)
        if mapped != raw.hex():
            dirty = True
            raw = bytes.fromhex(mapped)
        rebuilt.append((mode, name, raw))
    if not dirty:
        return content, False
    return _build_tree(rebuilt), True


def _rewrite_text(content: bytes, mapping: dict[str, str], prefixes: tuple[bytes, ...]) -> tuple[bytes, bool]:
    lines = content.split(b"\n")
    dirty = False
    out = []
    for line in lines:
        replaced = line
        for prefix in prefixes:
            if line.startswith(prefix):
                oid = line[len(prefix) :].decode()
                mapped = _resolve(oid, mapping)
                if mapped != oid:
                    dirty = True
                    replaced = prefix + mapped.encode()
                break
        out.append(replaced)
    if not dirty:
        return content, False
    return b"\n".join(out), True


def _parse_tree(body: bytes) -> list[tuple[bytes, bytes, bytes]]:
    entries = []
    index = 0
    while index < len(body):
        space = body.index(b" ", index)
        mode = body[index:space]
        end = body.index(b"\0", space)
        name = body[space + 1 : end]
        oid = body[end + 1 : end + 21]
        entries.append((mode, name, oid))
        index = end + 21
    return entries


def _build_tree(entries: list[tuple[bytes, bytes, bytes]]) -> bytes:
    out = b""
    for mode, name, oid in entries:
        out += mode + b" " + name + b"\0" + oid
    return out


def _reachable(tips: list[str], stored: dict[str, tuple[str, bytes]]) -> set[str]:
    seen: set[str] = set()
    stack = list(tips)
    while stack:
        oid = stack.pop()
        if oid in seen or oid not in stored:
            continue
        seen.add(oid)
        kind, content = stored[oid]
        if kind == "tree":
            stack.extend(raw.hex() for _, _, raw in _parse_tree(content))
        elif kind == "commit":
            for line in content.split(b"\n"):
                if line.startswith(b"tree ") or line.startswith(b"parent "):
                    stack.append(line.split()[1].decode())
        elif kind == "tag":
            for line in content.split(b"\n"):
                if line.startswith(b"object "):
                    stack.append(line.split()[1].decode())
                    break
    return seen


def _post_pin(content: bytes, name: str, jwt: str, endpoint: str) -> str:
    boundary = "algitpinboundary"
    body = (
        f"--{boundary}\r\n"
        f'Content-Disposition: form-data; name="file"; filename="{name}"\r\n'
        "Content-Type: application/octet-stream\r\n\r\n"
    ).encode() + content + f"\r\n--{boundary}--\r\n".encode()
    request = urllib.request.Request(endpoint, data=body, method="POST")
    request.add_header("Authorization", f"Bearer {jwt}")
    request.add_header("Content-Type", f"multipart/form-data; boundary={boundary}")
    with urllib.request.urlopen(request, timeout=60) as response:
        payload = json.loads(response.read().decode())
    cid = payload.get("IpfsHash") or payload.get("cid")
    if not cid:
        raise RuntimeError("Pinata did not return a CID")
    return str(cid)


def _dispenser(kmd) -> tuple[str, str]:
    wallets = kmd.list_wallets()
    wallet = next(item for item in wallets if item["name"] == "unencrypted-default-wallet")
    handle = kmd.init_wallet_handle(wallet["id"], "")
    address = kmd.list_keys(handle)[0]
    private = kmd.export_key(handle, "", address)
    kmd.release_wallet_handle(handle)
    return private, address


def _pay(algod, sender_key: str, sender: str, items: list[tuple[str, int, bytes]]) -> list[dict]:
    from algosdk import transaction
    from algosdk.error import AlgodHTTPError

    sent: list[dict] = []
    for offset in range(0, len(items), 16):
        batch = items[offset : offset + 16]
        base = algod.suggested_params()
        txns = []
        for receiver, amount, note in batch:
            if len(note) > 4096:
                raise ValueError(f"note is {len(note)} bytes")
            suggested = transaction.SuggestedParams(
                fee_for_note(len(note)) if note else 1000,
                base.first,
                base.last,
                base.gh,
                base.gen,
                True,
                base.consensus_version,
                base.min_fee,
            )
            txns.append(transaction.PaymentTxn(sender, suggested, receiver, amount, note=note or None))
        if len(txns) > 1:
            transaction.assign_group_id(txns)
        signed = [txn.sign(sender_key) for txn in txns]
        try:
            algod.send_transactions(signed)
        except AlgodHTTPError:
            base = algod.suggested_params()
            raise
        info = transaction.wait_for_confirmation(algod, signed[0].get_txid(), 40)
        confirmed = int(info["confirmed-round"])
        for txn, (receiver, _amount, note) in zip(txns, batch):
            sent.append({"txid": txn.get_txid(), "round": confirmed, "receiver": receiver, "note_len": len(note)})
    return sent


def _wait_indexer(round_number: int) -> None:
    import time

    deadline = time.time() + 60
    while time.time() < deadline:
        try:
            with urllib.request.urlopen(LOCAL_INDEXER + "/health", timeout=3) as response:
                health = json.loads(response.read().decode())
            if int(health.get("round") or 0) >= round_number:
                return
        except (urllib.error.URLError, TimeoutError, json.JSONDecodeError, ValueError):
            pass
        time.sleep(0.4)


def _frames_from_indexer(mailbox: str, indexer: str) -> list[dict]:
    token = ""
    rows = []
    while True:
        url = f"{indexer}/v2/transactions?address={mailbox}&tx-type=pay&limit=1000"
        if token:
            url += "&next=" + urllib.request.quote(token)
        with urllib.request.urlopen(url, timeout=30) as response:
            data = json.loads(response.read().decode())
        for tx in data.get("transactions") or []:
            pay = tx.get("payment-transaction") or {}
            if pay.get("receiver") != mailbox or not tx.get("note"):
                continue
            note = base64.b64decode(tx["note"])
            if note.startswith(MAGIC):
                rows.append((tx.get("confirmed-round") or 0, tx.get("intra-round-offset") or 0, note))
        token = data.get("next-token") or ""
        if not token:
            break
    rows.sort()
    return [_parse_frame(note) for _, _, note in rows]


def _preferred_ref(refs: dict[str, str], git_dir: str) -> str:
    """The branch a clone should open. A name may contain a slash."""
    heads = [(name, oid) for name, oid in refs.items() if name.startswith("refs/heads/")]
    if not heads:
        return next(iter(refs), "")
    tips = []
    for name, oid in heads:
        ancestor = False
        for _other_name, other in heads:
            if other == oid:
                continue
            check = subprocess.run(
                ["git", "--git-dir", git_dir, "merge-base", "--is-ancestor", oid, other],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
            if check.returncode == 0:
                ancestor = True
                break
        if not ancestor:
            tips.append((name, oid))
    if not tips:
        tips = heads

    def stamp(oid: str) -> int:
        when = subprocess.check_output(
            ["git", "--git-dir", git_dir, "log", "-1", "--format=%ct", oid],
            text=True,
        ).strip()
        return int(when or "0")

    name, _oid = max(tips, key=lambda item: (stamp(item[1]), item[0]))
    return name


def _checkout_work(git_dir: str, refs: dict[str, str], work: str) -> str:
    ref = _preferred_ref(refs, git_dir)
    if not ref:
        return ""
    subprocess.check_call(["git", "--git-dir", git_dir, "symbolic-ref", "HEAD", ref])
    branch = ref.removeprefix("refs/heads/")
    subprocess.check_call(["git", "clone", "--quiet", "--branch", branch, git_dir, work])
    return branch


def _overview(root: Path, receipt: dict) -> dict:
    branch = _git(str(root), "rev-parse", "--abbrev-ref", "HEAD").decode().strip()
    log = _git(str(root), "log", "--format=%H%x1f%an%x1f%at%x1f%s")
    commits = []
    for line in log.splitlines():
        oid, author, when, subject = line.decode().split("\x1f", 3)
        commits.append({"id": oid, "author": author, "at": int(when), "subject": subject})
    files = [line.decode() for line in _git(str(root), "ls-tree", "-r", "--name-only", "HEAD").splitlines()]
    return {
        "branch": branch,
        "mailbox": receipt.get("mailbox", ""),
        "network": receipt.get("network", ""),
        "commits": commits,
        "files": files,
    }


def _safe_path(path: str) -> str:
    if not path or path.startswith("/") or "\\" in path:
        raise ValueError("path escapes the repository")
    parts = path.split("/")
    if any(part in {"", ".", ".."} for part in parts):
        raise ValueError("path escapes the repository")
    return path


def _hexish(value: str) -> bool:
    if value == "HEAD":
        return True
    return 4 <= len(value) <= 64 and all(character in "0123456789abcdef" for character in value)


def _page(receipt: dict) -> str:
    blob = json.dumps(receipt).replace("<", "\\u003c")
    return PAGE.replace("/*RECEIPT*/", blob)


PAGE = """<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>ALGit</title>
  <style>
    :root {
      color-scheme: light;
      --field: #e4ebf0;
      --ink: #17202b;
      --rail: #1b3040;
      --rail-text: #e7eef3;
      --rust: #b8431f;
      --line: #c5d2db;
      --focus: #b8431f;
    }
    * { box-sizing: border-box; }
    html, body { margin: 0; height: 100%; }
    body {
      background: var(--field);
      color: var(--ink);
      font-family: "Avenir Next", "Segoe UI", sans-serif;
      font-size: 1.05rem;
      line-height: 1.45;
    }
    .visually-hidden:where(:not(:focus-within, :active)) {
      position: absolute !important;
      clip-path: inset(50%) !important;
      overflow: hidden !important;
      width: 1px !important;
      height: 1px !important;
      margin: -1px !important;
      padding: 0 !important;
      border: 0 !important;
      white-space: nowrap !important;
    }
    .skip:focus-within, a.skip:focus {
      position: fixed;
      top: 0.5rem;
      left: 0.5rem;
      z-index: 2;
      background: var(--field);
      color: var(--ink);
      padding: 0.4rem 0.7rem;
    }
    :where(a, button):focus-visible {
      outline: 3px solid var(--focus);
      outline-offset: 3px;
    }
    .shell {
      display: grid;
      grid-template-columns: 16rem minmax(0, 1fr);
      grid-template-areas: "rail main";
      min-height: 100dvh;
    }
    .rail { grid-area: rail; }
    main { grid-area: main; }
    @media (max-width: 40rem) {
      .shell {
        grid-template-columns: minmax(0, 1fr);
        grid-template-areas:
          "rail"
          "main";
      }
    }
    .rail {
      background: var(--rail);
      color: var(--rail-text);
      padding: 1.25rem 1rem 2rem;
    }
    .product { margin: 0; font-size: 1.4rem; }
    .branch { margin: 0.2rem 0 0.8rem; color: var(--rust); font-size: 1.15rem; }
    .mailbox { margin: 0 0 1.2rem; overflow-wrap: anywhere; font-family: ui-monospace, "SF Mono", monospace; font-size: 0.78rem; }
    .rail h2 { font-size: 1rem; font-weight: 600; margin: 1.2rem 0 0.4rem; }
    .rail ul { list-style: none; margin: 0; padding: 0; }
    .rail a {
      display: block;
      min-block-size: 1.5rem;
      padding: 0.2rem 0;
      color: var(--rail-text);
      text-decoration: none;
      overflow-wrap: anywhere;
    }
    .rail a[aria-current="page"] { text-decoration: underline; }
    main { padding: 1.5rem 1.6rem 3rem; min-width: 0; }
    h1 {
      font-family: Charter, "Iowan Old Style", Georgia, serif;
      font-weight: 500;
      font-size: 2rem;
      line-height: 1.2;
      margin: 0 0 0.6rem;
    }
    #meta { margin: 0 0 1rem; }
    pre {
      margin: 0;
      white-space: pre-wrap;
      overflow-wrap: anywhere;
      font-family: ui-monospace, "SF Mono", monospace;
      font-size: 0.86rem;
      line-height: 1.4;
    }
  </style>
</head>
<body>
  <a class="skip visually-hidden" href="#content">Skip to the commit</a>
  <div class="shell">
    <nav class="rail" aria-label="Repository">
      <p class="product">ALGit</p>
      <p class="branch" id="branch"></p>
      <p class="mailbox" id="mailbox"></p>
      <h2>Files</h2>
      <ul id="files"></ul>
      <h2>Commits</h2>
      <ul id="commits"></ul>
    </nav>
    <main id="content" tabindex="-1">
      <h1 id="subject"></h1>
      <p id="meta"></p>
      <pre id="body"></pre>
    </main>
  </div>
  <script>
    const receipt = /*RECEIPT*/;
    const files = document.getElementById("files");
    const commits = document.getElementById("commits");
    const subject = document.getElementById("subject");
    const meta = document.getElementById("meta");
    const body = document.getElementById("body");
    const branch = document.getElementById("branch");
    const mailbox = document.getElementById("mailbox");

    function link(parent, label, onClick) {
      const item = document.createElement("li");
      const anchor = document.createElement("a");
      anchor.href = "#";
      anchor.textContent = label;
      anchor.addEventListener("click", (event) => {
        event.preventDefault();
        onClick(anchor);
      });
      item.append(anchor);
      parent.append(item);
      return anchor;
    }

    function mark(anchor) {
      for (const node of document.querySelectorAll(".rail a")) node.removeAttribute("aria-current");
      anchor.setAttribute("aria-current", "page");
    }

    async function showFile(path, anchor) {
      mark(anchor);
      const response = await fetch("/api/file?path=" + encodeURIComponent(path));
      subject.textContent = path;
      meta.textContent = receipt.network ? receipt.network : "";
      body.textContent = await response.text();
    }

    async function showCommit(commit, anchor) {
      mark(anchor);
      const response = await fetch("/api/diff?rev=" + encodeURIComponent(commit.id));
      subject.textContent = commit.subject;
      const when = new Date(commit.at * 1000);
      meta.textContent = commit.author + ", " + when.toLocaleString();
      body.textContent = await response.text();
    }

    const overview = await fetch("/api/overview").then((response) => response.json());
    branch.textContent = overview.branch;
    mailbox.textContent = overview.mailbox || "This page is on this machine.";
    document.title = overview.branch + " · ALGit";
    let first = null;
    for (const path of overview.files) {
      link(files, path, (anchor) => showFile(path, anchor));
    }
    for (const commit of overview.commits) {
      const anchor = link(commits, commit.subject, (node) => showCommit(commit, node));
      if (!first) first = { commit, anchor };
    }
    if (first) showCommit(first.commit, first.anchor);
  </script>
</body>
</html>
"""
