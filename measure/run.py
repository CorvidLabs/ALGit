#!/usr/bin/env python3
"""Measure an AlgoChat mailbox as a Git remote on LocalNet.

Public notes are raw ALGT frames. Anyone can read them.
Private notes are AlgoChat group messages: 0x04 session, 0x06 key delivery,
0x07 file bytes. No second cipher.

Two write models:
  objects  content-addressed git objects, skip oids the mailbox already has
  deltas   same, except a changed blob is a binary delta of the previous blob
"""

from __future__ import annotations

import argparse
import base64
import hashlib
import json
import os
import shutil
import subprocess
import sys
import time
import urllib.error
import urllib.request
import warnings
import zlib

warnings.filterwarnings("ignore", category=DeprecationWarning)
from collections import defaultdict
from dataclasses import dataclass, field
from importlib.metadata import version as package_version
from pathlib import Path

# py-algorand-sdk 2.12.0 lives here so the harness does not import Homebrew's 2.11.1.
# 2.11.1 rejects any note longer than 1024 bytes. 2.12.0 does not: 1024 is only the
# fee-free allowance, and consensus allows 4096 with the section 10.3 surcharge.
PYDEPS = Path(__file__).resolve().parent / "pydeps"
sys.path.insert(0, str(PYDEPS))

from algosdk import account, encoding, transaction
from algosdk.error import AlgodHTTPError
from algosdk.kmd import KMDClient
from algosdk.v2client.algod import AlgodClient
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from cryptography.hazmat.primitives.serialization import Encoding, PublicFormat

SDK_VERSION = package_version("py-algorand-sdk")

ALGOCHAT_SRC = os.environ.get(
    "ALGOCHAT_SRC",
    "/Users/leif/Development/_CorvidLabs/algochat/py/src",
)
sys.path.insert(0, ALGOCHAT_SRC)

from algochat.group import open_group_message, seal_group_message  # noqa: E402
from algochat.group_admin import (  # noqa: E402
    OP_ADD_MEMBER,
    OP_CREATE,
    AdminEvent,
    delivery_authorized,
    draft_admin,
    open_group_key_delivery,
    reduce_admin,
    seal_group_key_delivery,
)
from algochat.keys import derive_keys_from_seed, public_key_to_bytes  # noqa: E402
from algochat.pq import (  # noqa: E402
    accept_pq_session,
    decrypt_pq_message,
    derive_mlkem_keypair,
    encode_pq_key_announcement,
    encrypt_pq_message,
    initiate_pq_session,
    parse_pq_key_announcement,
)
from algochat.types import PQError  # noqa: E402

TOKEN = "a" * 64
ALGOD_URL = "http://127.0.0.1:4001"
KMD_URL = "http://127.0.0.1:4002"
INDEXER_URL = "http://127.0.0.1:8980"
EVIDENCE = Path(__file__).resolve().parent / "evidence"

MAGIC = b"ALGT"
VERSION = 1
HEADER = 51
PUBLIC_CHUNK = 4096 - HEADER
PRIVATE_PLAINTEXT_MAX = 4026
PRIVATE_CHUNK = PRIVATE_PLAINTEXT_MAX - HEADER
ZERO_OID = b"\x00" * 20

KIND_OBJECT = 1
KIND_DELTA = 2
KIND_REF = 3
KIND_PULL = 4
KIND_ISSUE = 5
KIND_CI = 6
KIND_LOG = 7

KIND_NAME = {
    KIND_OBJECT: "object",
    KIND_DELTA: "delta",
    KIND_REF: "ref",
    KIND_PULL: "pull",
    KIND_ISSUE: "issue",
    KIND_CI: "ci",
    KIND_LOG: "log",
}


def fee_for_note(note_len: int, min_fee: int = 1000) -> int:
    """PROTOCOL.md section 10.3, Ed25519."""
    if note_len < 0 or note_len > 4096:
        raise ValueError(f"note length {note_len} is not legal")
    over = max(0, note_len - 1024)
    surcharge = (over * min_fee + 9999) // 10000
    return min_fee + surcharge


def encode_size(value: int) -> bytes:
    out = bytearray()
    while True:
        byte = value & 0x7F
        value >>= 7
        if value:
            out.append(byte | 0x80)
        else:
            out.append(byte)
            return bytes(out)


def read_size(buf: bytes, index: int) -> tuple[int, int]:
    value = 0
    shift = 0
    while True:
        byte = buf[index]
        index += 1
        value |= (byte & 0x7F) << shift
        if byte < 128:
            return value, index
        shift += 7
        if shift > 63:
            raise ValueError("size overflow")


def apply_delta(base: bytes, delta: bytes) -> bytes:
    base_size, index = read_size(delta, 0)
    result_size, index = read_size(delta, index)
    if base_size != len(base):
        raise ValueError(f"delta base size {base_size} != {len(base)}")
    out = bytearray()
    while index < len(delta):
        command = delta[index]
        index += 1
        if command == 0:
            raise ValueError("empty delta command")
        if command & 0x80:
            offset = 0
            size = 0
            for bit in range(4):
                if command & (1 << bit):
                    offset |= delta[index] << (8 * bit)
                    index += 1
            for bit in range(3):
                if command & (1 << (4 + bit)):
                    size |= delta[index] << (8 * bit)
                    index += 1
            if size == 0:
                size = 0x10000
            end = offset + size
            if end > len(base):
                raise ValueError("delta copy past base")
            out += base[offset:end]
        else:
            out += delta[index : index + command]
            index += command
    if len(out) != result_size:
        raise ValueError(f"delta produced {len(out)} bytes, wanted {result_size}")
    return bytes(out)


def binary_delta(base: bytes, target: bytes) -> bytes:
    """Git binary delta of target against base. Round-trips through apply_delta."""
    if len(base) <= 65536:
        step, block = 1, 16
    elif len(base) <= 1_048_576:
        step, block = 4, 16
    else:
        step, block = 32, 32
    index: dict[bytes, int] = {}
    if len(base) >= block:
        for offset in range(0, len(base) - block + 1, step):
            index.setdefault(base[offset : offset + block], offset)
    commands = bytearray()
    literals = bytearray()

    def flush_literals() -> None:
        start = 0
        while start < len(literals):
            take = min(127, len(literals) - start)
            commands.append(take)
            commands.extend(literals[start : start + take])
            start += take
        literals.clear()

    def emit_copy(offset: int, size: int) -> None:
        while size:
            take = min(size, 0xFFFF)
            command = 0x80
            body = bytearray()
            cursor = offset
            for bit in range(4):
                byte = cursor & 0xFF
                if byte:
                    command |= 1 << bit
                    body.append(byte)
                cursor >>= 8
            cursor = take
            for bit in range(3):
                byte = cursor & 0xFF
                if byte:
                    command |= 1 << (4 + bit)
                    body.append(byte)
                cursor >>= 8
            commands.append(command)
            commands.extend(body)
            offset += take
            size -= take

    position = 0
    while position < len(target):
        matched = 0
        match_at = 0
        if position + block <= len(target):
            found = index.get(target[position : position + block])
            if found is not None:
                matched = block
                match_at = found
                while (
                    position + matched < len(target)
                    and match_at + matched < len(base)
                    and target[position + matched] == base[match_at + matched]
                ):
                    matched += 1
                back = 0
                while (
                    back < len(literals)
                    and match_at - back - 1 >= 0
                    and literals[-1 - back] == base[match_at - back - 1]
                ):
                    back += 1
                if back:
                    del literals[-back:]
                    match_at -= back
                    matched += back
        if matched >= block:
            flush_literals()
            emit_copy(match_at, matched)
            position += matched - back
        else:
            literals.append(target[position])
            position += 1
    flush_literals()
    encoded = encode_size(len(base)) + encode_size(len(target)) + bytes(commands)
    if apply_delta(base, encoded) != target:
        raise RuntimeError("delta round-trip failed")
    return encoded


def self_test_delta() -> None:
    samples = [
        (b"", b""),
        (b"abc", b"abc"),
        (b"hello\n", b"hello\nworld\n"),
        (bytes(range(256)) * 40, bytes(range(256)) * 3 + b"XYZ" + bytes(range(256)) * 37),
        (b"line\n" * 1000, b"line\n" * 200 + b"CHANGED\n" + b"line\n" * 800),
        (os.urandom(60000), os.urandom(60000)),
        (b"x" * 100 + os.urandom(50), b"x" * 100 + os.urandom(50)),
    ]
    changed = binary_delta(b"line\n" * 1000, b"line\n" * 200 + b"CHANGED\n" + b"line\n" * 800)
    if len(changed) > 400:
        raise RuntimeError(f"one-line delta is {len(changed)} bytes, expected a small patch")
    for base, target in samples:
        produced = apply_delta(base, binary_delta(base, target))
        if produced != target:
            raise RuntimeError("delta self-test mismatch")
    table = {1024: 1000, 2000: 1098, 4096: 1308}
    for size, expect in table.items():
        got = fee_for_note(size)
        if got != expect:
            raise RuntimeError(f"fee for {size} is {got}, protocol table says {expect}")
    parts = tuple(int(piece) for piece in SDK_VERSION.split(".")[:3])
    if parts < (2, 12, 0):
        raise RuntimeError(
            f"py-algorand-sdk {SDK_VERSION} rejects notes over 1024 bytes; need 2.12.0"
        )
    if len(transaction.Transaction.as_note(b"\x00" * 4096)) != 4096:
        raise RuntimeError(f"py-algorand-sdk {SDK_VERSION} did not accept a 4096-byte note")


def canonical(kind: str, content: bytes) -> bytes:
    return f"{kind} {len(content)}\0".encode() + content


def sha1(data: bytes) -> bytes:
    return hashlib.sha1(data).digest()


def frame(kind: int, oid: bytes, base: bytes, index: int, count: int, payload: bytes) -> bytes:
    if len(oid) != 20 or len(base) != 20:
        raise ValueError("sha1 oids are 20 bytes")
    if not 0 <= index < 65536 or not 1 <= count <= 65536:
        raise ValueError(f"bad chunk {index}/{count}")
    return (
        MAGIC
        + bytes([VERSION, kind, 0])
        + oid
        + base
        + index.to_bytes(2, "big")
        + count.to_bytes(2, "big")
        + payload
    )


def parse_frame(data: bytes) -> dict:
    if len(data) < HEADER or data[:4] != MAGIC or data[4] != VERSION:
        raise ValueError("not an ALGT frame")
    return {
        "kind": data[5],
        "flags": data[6],
        "oid": data[7:27],
        "base": data[27:47],
        "index": int.from_bytes(data[47:49], "big"),
        "count": int.from_bytes(data[49:51], "big"),
        "payload": data[HEADER:],
    }


def chunk_payload(kind: int, oid: bytes, base: bytes, payload: bytes, width: int) -> list[bytes]:
    if width < 1:
        raise ValueError("chunk width")
    pieces = [payload[i : i + width] for i in range(0, max(len(payload), 1), width)]
    if payload == b"":
        pieces = [b""]
    count = len(pieces)
    return [frame(kind, oid, base, index, count, piece) for index, piece in enumerate(pieces)]


@dataclass
class Piece:
    kind: int
    oid: str
    base: str
    payload: bytes
    label: str


@dataclass
class Plan:
    name: str
    model: str
    private: bool
    pieces: list[Piece]
    skipped_oids: int
    object_count: int
    payload_bytes: int

    def notes(self) -> list[bytes]:
        width = PRIVATE_CHUNK if self.private else PUBLIC_CHUNK
        notes: list[bytes] = []
        for piece in self.pieces:
            oid = bytes.fromhex(piece.oid) if piece.oid else ZERO_OID
            base = bytes.fromhex(piece.base) if piece.base else ZERO_OID
            if len(oid) != 20:
                oid = ZERO_OID
            if len(base) != 20:
                base = ZERO_OID
            notes.extend(chunk_payload(piece.kind, oid, base, piece.payload, width))
        return notes


def git(repo: str, *args: str, input_bytes: bytes | None = None) -> bytes:
    result = subprocess.run(
        ["git", "-C", repo, *args],
        input=input_bytes,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )
    if result.returncode != 0:
        raise RuntimeError(result.stderr.decode() or f"git {' '.join(args)} failed")
    return result.stdout


def load_objects(repo: str, rev_args: list[str]) -> dict[str, tuple[str, bytes]]:
    listed = git(repo, "rev-list", "--objects", *rev_args)
    oids = []
    seen = set()
    for line in listed.splitlines():
        oid = line.split()[0].decode()
        if oid not in seen:
            seen.add(oid)
            oids.append(oid)
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
        if not header:
            break
        if header.endswith(b" missing\n"):
            continue
        got, kind, size_text = header.split()
        content = read_exact(int(size_text))
        if read_exact(1) != b"\n":
            raise RuntimeError("cat-file framing")
        raw = canonical(kind.decode(), content)
        digest = sha1(raw).hex()
        if digest != got.decode():
            raise RuntimeError(f"{got.decode()} is not sha1 of its canonical object")
        found[got.decode()] = (kind.decode(), content)
    proc.stdin.close()
    proc.wait()
    return found


def ref_map(repo: str) -> list[tuple[str, str]]:
    """Map origin branches onto refs/heads and local tags onto refs/tags."""
    refs: list[tuple[str, str]] = []
    remote = git(repo, "for-each-ref", "--format=%(objectname) %(refname)", "refs/remotes/origin")
    for line in remote.splitlines():
        oid, name = line.decode().split(" ", 1)
        if name == "refs/remotes/origin/HEAD":
            continue
        if not name.startswith("refs/remotes/origin/"):
            continue
        refs.append((f"refs/heads/{name.removeprefix('refs/remotes/origin/')}", oid))
    tags = git(repo, "for-each-ref", "--format=%(objectname) %(refname)", "refs/tags")
    for line in tags.splitlines():
        if not line.strip():
            continue
        oid, name = line.decode().split(" ", 1)
        refs.append((name, oid))
    return refs


def parse_diff_tree(repo: str, commit: str, parent: str | None) -> list[tuple[str, str, str, str]]:
    """Diff a commit against its first parent as two trees.

    `git diff-tree <merge>` with no `-m` prints no file lines, so a blob that
    first appears in a merge result is dropped. Two tree-ish arguments show
    the tree the commit recorded.
    """
    args = ["diff-tree", "-r", "--raw", "-M", "--no-commit-id", "-z"]
    if parent is None:
        args.extend(["--root", commit])
    else:
        args.extend([parent, commit])
    data = git(repo, *args)
    parts = data.split(b"\0")
    records = []
    index = 0
    while index < len(parts):
        header = parts[index]
        if not header:
            break
        if not header.startswith(b":"):
            index += 1
            continue
        text = header.decode()
        fields = text[1:].split()
        old_oid, new_oid, status = fields[2], fields[3], fields[4]
        path = parts[index + 1].decode()
        index += 2
        if status[0] in {"R", "C"}:
            path = parts[index].decode()
            index += 1
        records.append((status, old_oid, new_oid, path))
    return records


def plan_history(
    repo: str,
    objects: dict[str, tuple[str, bytes]],
    commits: list[str],
    model: str,
    have: set[str],
) -> tuple[list[Piece], int]:
    """Return pieces for objects not in have. Model deltas replaces changed blobs."""
    parents = {}
    for commit in commits:
        text = git(repo, "rev-parse", f"{commit}^@").decode().split()
        parents[commit] = text
    pieces: list[Piece] = []
    skipped = 0
    stored = set(have)
    blob_encoding: dict[str, tuple[str, bytes]] = {}

    def add_full(oid: str) -> None:
        nonlocal skipped
        if oid in stored:
            skipped += 1
            return
        kind, content = objects[oid]
        stored.add(oid)
        pieces.append(Piece(KIND_OBJECT, oid, "", canonical(kind, content), kind))

    for oid, (kind, _content) in objects.items():
        if kind != "blob":
            add_full(oid)

    if model == "deltas":
        for number, commit in enumerate(commits, start=1):
            if number == 1 or number % 50 == 0 or number == len(commits):
                print(f"  delta commit {number}/{len(commits)}", flush=True)
            parent = parents[commit][0] if parents[commit] else None
            for status, old_oid, new_oid, _path in parse_diff_tree(repo, commit, parent):
                if new_oid not in objects or objects[new_oid][0] != "blob":
                    continue
                if new_oid in stored or new_oid in blob_encoding:
                    continue
                previous = None
                if status[0] in {"M", "R", "C"} and old_oid in objects:
                    previous = old_oid
                if previous is None:
                    add_full(new_oid)
                    continue
                _old_kind, old_content = objects[previous]
                _new_kind, new_content = objects[new_oid]
                delta = binary_delta(old_content, new_content)
                full = canonical("blob", new_content)
                if len(delta) < len(full):
                    blob_encoding[new_oid] = (previous, delta)
                    stored.add(new_oid)
                else:
                    add_full(new_oid)
        for oid, (base, delta) in blob_encoding.items():
            pieces.append(Piece(KIND_DELTA, oid, base, delta, "blob-delta"))
    else:
        for oid, (kind, _content) in objects.items():
            if kind == "blob":
                add_full(oid)
    return pieces, skipped


def commits_topo(repo: str, rev_args: list[str]) -> list[str]:
    text = git(repo, "rev-list", "--reverse", "--topo-order", *rev_args).decode().split()
    return text


def make_plan(
    name: str,
    repo: str,
    rev_args: list[str],
    model: str,
    private: bool,
    have: set[str] | None = None,
    extra_commits: list[str] | None = None,
) -> Plan:
    have = have or set()
    objects = load_objects(repo, rev_args)
    if extra_commits is not None:
        commit_list = extra_commits
    else:
        commit_list = commits_topo(repo, rev_args)
    pieces, skipped = plan_history(repo, objects, commit_list, model, have)
    for refname, oid in ref_map(repo):
        if extra_commits is not None:
            continue
        pieces.append(Piece(KIND_REF, oid, "", refname.encode(), "ref"))
    payload_bytes = sum(len(piece.payload) for piece in pieces)
    return Plan(name, model, private, pieces, skipped, len(objects), payload_bytes)


def plan_fee(plan: Plan) -> dict:
    plain = plan.notes()
    if plan.private:
        notes = [b"\x00" * (len(item) + 70) for item in plain]
        # 0x07 adds a 54-byte header and a 16-byte tag around the plaintext frame.
        note_lengths = [len(item) + 70 for item in plain]
    else:
        note_lengths = [len(item) for item in plain]
    fees = [fee_for_note(length) for length in note_lengths]
    by_kind: dict[str, int] = defaultdict(int)
    width = PRIVATE_CHUNK if plan.private else PUBLIC_CHUNK
    for piece in plan.pieces:
        count = max(1, (len(piece.payload) + width - 1) // width)
        by_kind[KIND_NAME[piece.kind]] += count
    return {
        "pieces": len(plan.pieces),
        "notes": len(note_lengths),
        "note_bytes": sum(note_lengths),
        "payload_bytes": plan.payload_bytes,
        "fee_microalgo": sum(fees),
        "objects": plan.object_count,
        "skipped_oids": plan.skipped_oids,
        "by_kind": dict(by_kind),
        "max_note": max(note_lengths) if note_lengths else 0,
        "min_note": min(note_lengths) if note_lengths else 0,
        "plain_bytes": sum(len(item) for item in plain),
    }


@dataclass
class Party:
    address: str
    private_key: str
    seed: bytes
    x_private: object
    x_public: object
    kem: object

    @classmethod
    def generate(cls) -> "Party":
        private_key, address = account.generate_account()
        raw = base64.b64decode(private_key)
        seed = raw[:32]
        x_private, x_public = derive_keys_from_seed(seed)
        kem = derive_mlkem_keypair(seed)
        ed = Ed25519PrivateKey.from_private_bytes(seed)
        pub = ed.public_key().public_bytes(Encoding.Raw, PublicFormat.Raw)
        if pub != encoding.decode_address(address):
            raise RuntimeError("ed25519 seed does not match the Algorand address")
        return cls(address, private_key, seed, x_private, x_public, kem)

    def pubkey(self) -> bytes:
        return encoding.decode_address(self.address)

    def ed25519(self) -> Ed25519PrivateKey:
        return Ed25519PrivateKey.from_private_bytes(self.seed)


@dataclass
class Sent:
    txid: str
    round: int
    fee: int
    note_len: int
    sender: str
    receiver: str
    label: str
    note: bytes


class Chain:
    def __init__(self) -> None:
        self.algod = AlgodClient(TOKEN, ALGOD_URL)
        self.kmd = KMDClient(TOKEN, KMD_URL)
        self._params: transaction.SuggestedParams | None = None
        self._params_at = -1

    def status_round(self) -> int:
        return int(self.algod.status()["last-round"])

    def params(self, force: bool = False) -> transaction.SuggestedParams:
        current = self.status_round()
        if force or self._params is None or current + 50 > self._params.last:
            self._params = self.algod.suggested_params()
            self._params_at = current
        return self._params

    def dispenser(self) -> tuple[str, str]:
        wallets = self.kmd.list_wallets()
        wallet = next(item for item in wallets if item["name"] == "unencrypted-default-wallet")
        handle = self.kmd.init_wallet_handle(wallet["id"], "")
        keys = self.kmd.list_keys(handle)
        address = keys[0]
        private = self.kmd.export_key(handle, "", address)
        self.kmd.release_wallet_handle(handle)
        return private, address

    def submit(
        self,
        sender: Party,
        items: list[tuple[str, int, bytes, str]],
        force_fee: int | None = None,
        _retry: bool = True,
    ) -> list[Sent]:
        """Send payments. items are (receiver, amount, note, label). Confirms the group."""
        if not items:
            return []
        if len(items) > 16:
            raise ValueError("group limit is 16")
        base = self.params()
        txns = []
        for receiver, amount, note, _label in items:
            if len(note) > 4096:
                raise ValueError(f"note is {len(note)} bytes")
            cost = force_fee if force_fee is not None else (fee_for_note(len(note)) if note else 1000)
            suggested = transaction.SuggestedParams(
                cost,
                base.first,
                base.last,
                base.gh,
                base.gen,
                True,
                base.consensus_version,
                base.min_fee,
            )
            txns.append(
                transaction.PaymentTxn(sender.address, suggested, receiver, amount, note=note or None)
            )
        if len(txns) > 1:
            transaction.assign_group_id(txns)
        signed = [txn.sign(sender.private_key) for txn in txns]
        txids = [txn.get_txid() for txn in txns]
        try:
            self.algod.send_transactions(signed)
        except AlgodHTTPError as exc:
            text = str(exc)
            # Refresh suggested rounds after a stale window. Do not retry a fee
            # rejection: an underpay must stay rejected, and a wrong surcharge
            # must not loop.
            if _retry and "txn dead" in text:
                self.params(force=True)
                return self.submit(sender, items, force_fee=force_fee, _retry=False)
            raise
        info = transaction.wait_for_confirmation(self.algod, txids[0], 40)
        confirmed = int(info["confirmed-round"])
        sent = []
        for txn, txid, (receiver, _amount, note, label) in zip(txns, txids, items):
            sent.append(
                Sent(
                    txid=txid,
                    round=confirmed,
                    fee=int(txn.fee),
                    note_len=len(note),
                    sender=sender.address,
                    receiver=receiver,
                    label=label,
                    note=note,
                )
            )
        return sent

    def submit_all(self, sender: Party, items: list[tuple[str, int, bytes, str]]) -> list[Sent]:
        sent: list[Sent] = []
        started = time.perf_counter()
        total = len(items)
        for offset in range(0, total, 16):
            batch = items[offset : offset + 16]
            try:
                sent.extend(self.submit(sender, batch))
            except AlgodHTTPError as exc:
                if "fee" in str(exc).lower() or "overspend" in str(exc).lower():
                    raise
                self.params(force=True)
                sent.extend(self.submit(sender, batch))
            done = len(sent)
            if done == total or done % 512 == 0:
                elapsed = time.perf_counter() - started
                rate = done / elapsed if elapsed else 0
                print(f"  submitted {done}/{total} in {elapsed:.1f}s ({rate:.0f} notes/s)", flush=True)
        return sent

    def block_notes(self, rounds: list[int], receivers: set[str]) -> list[tuple[int, int, str, str, bytes, int]]:
        """Return (round, offset, sender, receiver, note, fee) for payments to receivers."""
        found = []
        unique = sorted(set(rounds))
        for number in unique:
            raw = self.algod.block_info(number, response_format="json")
            txns = raw.get("block", raw).get("txns") or []
            for offset, wrapped in enumerate(txns):
                inner = wrapped.get("txn", wrapped)
                if inner.get("type") != "pay":
                    continue
                receiver = as_address(inner.get("rcv"))
                sender = as_address(inner.get("snd"))
                if receiver not in receivers:
                    continue
                note_field = inner.get("note")
                note = b""
                if isinstance(note_field, str):
                    note = base64.b64decode(note_field)
                elif isinstance(note_field, (bytes, bytearray)):
                    note = bytes(note_field)
                fee = int(inner.get("fee") or 0)
                found.append((number, offset, sender, receiver, note, fee))
        return found


def as_address(value: object) -> str:
    if not isinstance(value, str) or not value:
        return ""
    if len(value) == 58:
        return value
    try:
        raw = base64.b64decode(value)
    except Exception:
        return value
    if len(raw) == 32:
        return encoding.encode_address(raw)
    return value


def txid_raw(txid: str) -> bytes:
    padded = txid + "=" * ((8 - len(txid) % 8) % 8)
    raw = base64.b32decode(padded)
    if len(raw) != 32:
        raise RuntimeError(f"txid {txid} decoded to {len(raw)} bytes")
    return raw


def write_jsonl(path: Path, rows: list[Sent]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w") as handle:
        for row in rows:
            handle.write(
                json.dumps(
                    {
                        "txid": row.txid,
                        "round": row.round,
                        "fee": row.fee,
                        "note_len": row.note_len,
                        "sender": row.sender,
                        "receiver": row.receiver,
                        "label": row.label,
                    }
                )
                + "\n"
            )


def summarize_sent(rows: list[Sent]) -> dict:
    if not rows:
        return {"notes": 0, "fee_microalgo": 0, "note_bytes": 0}
    return {
        "notes": len(rows),
        "fee_microalgo": sum(row.fee for row in rows),
        "note_bytes": sum(row.note_len for row in rows),
        "first_txid": rows[0].txid,
        "last_txid": rows[-1].txid,
        "first_round": min(row.round for row in rows),
        "last_round": max(row.round for row in rows),
        "rounds": len({row.round for row in rows}),
        "max_note": max(row.note_len for row in rows),
        "min_note": min(row.note_len for row in rows),
    }


def seal_private(plaintext: bytes, group_key: bytes, group_id: bytes, epoch: int, counter: int, sender: bytes) -> bytes:
    if len(plaintext) > PRIVATE_PLAINTEXT_MAX:
        raise ValueError(f"plaintext {len(plaintext)} exceeds {PRIVATE_PLAINTEXT_MAX}")
    return seal_group_message(plaintext, group_key, group_id, epoch, counter, sender)


def assemble(frames: list[dict]) -> dict[tuple[int, bytes], bytes]:
    grouped: dict[tuple[int, bytes], list[dict]] = defaultdict(list)
    for item in frames:
        grouped[(item["kind"], item["oid"])].append(item)
    built = {}
    for key, chunks in grouped.items():
        chunks.sort(key=lambda item: item["index"])
        count = chunks[0]["count"]
        if len(chunks) != count or [item["index"] for item in chunks] != list(range(count)):
            raise RuntimeError(f"incomplete object {key[1].hex()} kind {key[0]}")
        if any(item["base"] != chunks[0]["base"] for item in chunks):
            raise RuntimeError("delta base changed between chunks")
        built[key] = b"".join(item["payload"] for item in chunks)
        built[(key[0], key[1], b"base")] = chunks[0]["base"]
    return built


def materialize(frames: list[dict], out_dir: Path) -> dict:
    grouped_payloads: dict[tuple[int, bytes], bytes] = {}
    bases: dict[tuple[int, bytes], bytes] = {}
    buckets: dict[tuple[int, bytes], list[dict]] = defaultdict(list)
    # A ref note's oid is the target commit, so several refs share one oid.
    # Each ref is its own note. Objects and deltas are the things that chunk.
    ref_frames = []
    for item in frames:
        if item["kind"] == KIND_REF:
            ref_frames.append(item)
            continue
        buckets[(item["kind"], item["oid"])].append(item)
    for key, chunks in buckets.items():
        chunks.sort(key=lambda item: item["index"])
        count = chunks[0]["count"]
        indexes = [chunk["index"] for chunk in chunks]
        if indexes != list(range(count)):
            raise RuntimeError(
                f"missing chunk for kind {key[0]} {key[1].hex()}: got {indexes}, count {count}"
            )
        grouped_payloads[key] = b"".join(chunk["payload"] for chunk in chunks)
        bases[key] = chunks[0]["base"]
    blobs: dict[bytes, bytes] = {}
    objects: dict[bytes, bytes] = {}
    for (kind, oid), payload in grouped_payloads.items():
        if kind == KIND_OBJECT:
            if sha1(payload) != oid:
                raise RuntimeError(f"object {oid.hex()} failed sha1")
            objects[oid] = payload
            if payload.startswith(b"blob "):
                header, content = payload.split(b"\0", 1)
                blobs[oid] = content
        elif kind == KIND_REF:
            continue
    pending = [oid for (kind, oid) in grouped_payloads if kind == KIND_DELTA]
    while pending:
        # One pass applies every delta whose base blob is already known.
        # A rename chain is a stack of deltas, so a single left-to-right walk
        # is not enough and a fixed iteration cap gives up while bases remain.
        waiting = []
        resolved = 0
        for oid in pending:
            base = bases[(KIND_DELTA, oid)]
            if base not in blobs:
                waiting.append(oid)
                continue
            content = apply_delta(blobs[base], grouped_payloads[(KIND_DELTA, oid)])
            raw = canonical("blob", content)
            if sha1(raw) != oid:
                raise RuntimeError(f"delta {oid.hex()} reconstructed to {sha1(raw).hex()}")
            blobs[oid] = content
            objects[oid] = raw
            resolved += 1
        if resolved == 0:
            stuck = waiting[0]
            base = bases[(KIND_DELTA, stuck)]
            raise RuntimeError(
                f"unresolved deltas ({len(waiting)}), next {stuck.hex()} base {base.hex()}"
            )
        pending = waiting
    git_dir = out_dir / "repo.git"
    if git_dir.exists():
        shutil.rmtree(git_dir)
    subprocess.check_call(["git", "init", "--bare", "-q", str(git_dir)])
    for oid, raw in objects.items():
        digest = oid.hex()
        path = git_dir / "objects" / digest[:2] / digest[2:]
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(zlib.compress(raw))
    refs = []
    for item in ref_frames:
        if item["count"] != 1 or item["index"] != 0:
            raise RuntimeError(f"ref {item['payload']!r} spanned more than one note")
        refs.append((item["payload"].decode(), item["oid"].hex()))
    # Last frame in chain order wins. frames are already in chain order;
    # later refs overwrite earlier ones when we walk in order.
    latest: dict[str, str] = {}
    for name, oid in refs:
        latest[name] = oid
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


def frames_from_private(records: list[tuple[int, int, str, bytes]], group_key: bytes, sender: bytes) -> tuple[list[dict], list[str]]:
    """Open 0x07 notes in chain order. Returns frames and rejection reasons."""
    ordered = sorted(records, key=lambda item: (item[0], item[1], item[2]))
    accepted: list[tuple[int, int]] = []
    frames = []
    rejected = []
    for _round, _offset, _txid, note in ordered:
        if len(note) < 2 or note[0] != 0x02 or note[1] != 0x07:
            continue
        try:
            opened = open_group_message(note, group_key, sender, accepted)
        except PQError as exc:
            rejected.append(str(exc))
            continue
        accepted.append((opened.epoch, opened.counter))
        if opened.plaintext.startswith(MAGIC):
            frames.append(parse_frame(opened.plaintext))
    return frames, rejected


def frames_from_public(records: list[tuple[int, int, bytes]]) -> list[dict]:
    frames = []
    for _round, _offset, note in sorted(records, key=lambda item: (item[0], item[1])):
        if note.startswith(MAGIC):
            frames.append(parse_frame(note))
    return frames


def verify_edit_frames(
    chain: Chain,
    rows: list[Sent],
    mailbox: str,
    private: bool,
    group_key: bytes | None,
    owner: Party,
    repo: str,
) -> int:
    """Rebuild this push from the blocks and check each oid against git."""
    if private:
        frames, _rejected, _info = readback_private(
            chain, rows, mailbox, group_key or b"", owner.address, owner.pubkey()
        )
    else:
        frames, _info = readback_public(chain, rows, mailbox)
    buckets: dict[tuple[int, bytes], list[dict]] = defaultdict(list)
    for item in frames:
        buckets[(item["kind"], item["oid"])].append(item)
    checked = 0
    for (kind, oid), chunks in buckets.items():
        chunks.sort(key=lambda item: item["index"])
        payload = b"".join(item["payload"] for item in chunks)
        if kind == KIND_OBJECT:
            if sha1(payload) != oid:
                raise RuntimeError(f"edit object {oid.hex()} failed sha1")
        elif kind == KIND_DELTA:
            base = chunks[0]["base"]
            content = git(repo, "cat-file", "blob", base.hex())
            rebuilt = canonical("blob", apply_delta(content, payload))
            if sha1(rebuilt) != oid:
                raise RuntimeError(f"edit delta {oid.hex()} failed sha1")
        elif kind == KIND_REF:
            if payload.decode() != "refs/heads/measure":
                raise RuntimeError(payload.decode())
        else:
            continue
        checked += 1
    if checked == 0:
        raise RuntimeError("edit readback produced no frames")
    return checked


def pack_size(repo: str, rev_args: list[str]) -> int:
    listed = git(repo, "rev-list", "--objects", *rev_args)
    pack = subprocess.run(
        ["git", "-C", repo, "pack-objects", "--stdout", "--delta-base-offset", "-q"],
        input=listed,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )
    if pack.returncode != 0:
        raise RuntimeError(pack.stderr.decode())
    return len(pack.stdout)


def github_disk() -> dict:
    raw = subprocess.check_output(
        [
            "gh",
            "repo",
            "list",
            "CorvidLabs",
            "--limit",
            "400",
            "--json",
            "name,diskUsage,isPrivate,isFork,isArchived",
        ]
    )
    repos = json.loads(raw)
    named = ["site", "peck", "Roost", "3md", "Talon", "algochat", "jay.corvid.algo", "corvid-dress"]
    return {
        "repos": len(repos),
        "disk_usage_kb": sum(item["diskUsage"] or 0 for item in repos),
        "private": sum(1 for item in repos if item["isPrivate"]),
        "public": sum(1 for item in repos if not item["isPrivate"]),
        "archived": sum(1 for item in repos if item["isArchived"]),
        "forks": sum(1 for item in repos if item["isFork"]),
        "named_kb": {item["name"]: item["diskUsage"] for item in repos if item["name"] in named},
    }


def clone_work(source: str, dest: str) -> None:
    if Path(dest).exists():
        shutil.rmtree(dest)
    subprocess.check_call(["git", "clone", "--quiet", source, dest])


def commit_file(repo: str, path: str, content: bytes, message: str) -> str:
    target = Path(repo) / path
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(content)
    git(repo, "add", path)
    git(
        repo,
        "-c",
        "user.email=algit@example.invalid",
        "-c",
        "user.name=ALGit",
        "commit",
        "-q",
        "-m",
        message,
    )
    return git(repo, "rev-parse", "HEAD").decode().strip()


def reach(repo: str, commit: str) -> list[str]:
    return [commit]


def incremental_plan(
    name: str,
    repo: str,
    commit: str,
    model: str,
    private: bool,
    have: set[str],
    refname: str,
) -> Plan:
    objects = load_objects(repo, [commit])
    # Only the new commit needs a history walk. Parent blobs must already be in `objects`
    # because they are reachable from the commit. have skips oids already on the mailbox.
    pieces, skipped = plan_history(repo, objects, [commit], model, have)
    # plan_history also emits every tree and commit reachable from this commit.
    # have filters those. Drop pieces whose oid is already stored.
    fresh = [piece for piece in pieces if piece.oid not in have]
    skipped += len(pieces) - len(fresh)
    fresh.append(Piece(KIND_REF, commit, "", refname.encode(), "ref"))
    payload_bytes = sum(len(piece.payload) for piece in fresh)
    return Plan(name, model, private, fresh, skipped, len(objects), payload_bytes)


def have_oids(plan: Plan) -> set[str]:
    return {piece.oid for piece in plan.pieces if piece.kind in {KIND_OBJECT, KIND_DELTA} and piece.oid}


def private_items(
    plain_notes: list[bytes],
    labels: list[str],
    mailbox: str,
    group_key: bytes,
    group_id: bytes,
    sender: bytes,
    counter: int,
) -> tuple[list[tuple[str, int, bytes, str]], int]:
    items = []
    for plain, label in zip(plain_notes, labels):
        note = seal_private(plain, group_key, group_id, 1, counter, sender)
        items.append((mailbox, 0, note, label))
        counter += 1
    return items, counter


def labels_for(plan: Plan) -> list[str]:
    width = PRIVATE_CHUNK if plan.private else PUBLIC_CHUNK
    labels = []
    for piece in plan.pieces:
        count = max(1, (len(piece.payload) + width - 1) // width) if piece.payload else 1
        for index in range(count):
            labels.append(f"{KIND_NAME[piece.kind]}:{piece.oid[:12]}:{index}")
    return labels


def run_probe(chain: Chain, writer: Party, sink: str) -> dict:
    print("fee probe", flush=True)
    under_note = b"U" * 4096
    try:
        chain.submit(writer, [(sink, 0, under_note, "underpay-should-fail")], force_fee=1000)
    except AlgodHTTPError as exc:
        under_error = str(exc)
    else:
        under_error = ""
    full = chain.submit(writer, [(sink, 0, b"F" * 4096, "full-4096")])
    exact = chain.submit(writer, [(sink, 0, b"E" * 1024, "exact-1024")])
    over = chain.submit(writer, [(sink, 0, b"O" * 1025, "just-over-1024")])
    fetched = chain.block_notes([full[0].round], {sink})
    matched = [note for *_rest, note, _fee in [(row[0], row[1], row[2], row[3], row[4], row[5]) for row in fetched] if note == full[0].note]
    # rewrite clearer
    matched = [row for row in fetched if row[4] == full[0].note]
    return {
        "underpay_rejected": bool(under_error) and not under_error.startswith("sent"),
        "underpay_error": under_error.splitlines()[0][:500],
        "full_4096": summarize_sent(full),
        "exact_1024": summarize_sent(exact),
        "just_over_1024": summarize_sent(over),
        "full_note_refetched": bool(matched),
        "full_fee": full[0].fee,
        "exact_fee": exact[0].fee,
        "over_fee": over[0].fee,
    }


def setup_room(chain: Chain, owner: Party, member: Party, outsider: Party) -> dict:
    print("room setup", flush=True)
    mailbox = Party.generate()
    rows: list[Sent] = []
    rows += chain.submit(owner, [(mailbox.address, 100_000, b"", "fund-mailbox")])
    rows += chain.submit(owner, [(member.address, 200_000, b"", "fund-member")])
    rows += chain.submit(owner, [(outsider.address, 200_000, b"", "fund-outsider")])
    announce_owner = encode_pq_key_announcement(owner.kem.encaps_key, owner.ed25519())
    announce_member = encode_pq_key_announcement(member.kem.encaps_key, member.ed25519())
    rows += chain.submit(owner, [(owner.address, 0, announce_owner, "announce-owner")])
    rows += chain.submit(member, [(member.address, 0, announce_member, "announce-member")])
    parsed = parse_pq_key_announcement(announce_owner, owner.ed25519().public_key())
    if parsed is None or not parsed.is_verified:
        raise RuntimeError("owner announcement did not verify")

    handshake, owner_session = initiate_pq_session(
        owner.x_public,
        member.x_public,
        member.kem.encaps_key,
        owner.kem.encaps_key,
    )
    if len(handshake) != 2366:
        raise RuntimeError(f"handshake is {len(handshake)} bytes")
    rows += chain.submit(owner, [(member.address, 0, handshake, "0x04")])
    member_session = accept_pq_session(handshake, member.x_private, member.x_public, member.kem)
    if member_session.session_key != owner_session.session_key:
        raise RuntimeError("member session key does not match owner")
    try:
        accept_pq_session(handshake, outsider.x_private, outsider.x_public, outsider.kem)
        outsider_handshake = "opened"
    except PQError as exc:
        outsider_handshake = str(exc)
    session_text = "ALGit session ready"
    message = encrypt_pq_message(session_text, owner_session)
    rows += chain.submit(owner, [(member.address, 0, message, "0x05")])
    if decrypt_pq_message(message, member_session) != session_text:
        raise RuntimeError("member could not open 0x05")
    try:
        decrypt_pq_message(message, accept_pq_session(handshake, outsider.x_private, outsider.x_public, outsider.kem))
        outsider_message = "opened"
    except PQError as exc:
        outsider_message = str(exc)

    group_id = os.urandom(32)
    group_key = os.urandom(32)
    mailbox_key = mailbox.pubkey()
    create_note = draft_admin(
        None,
        OP_CREATE,
        owner.pubkey(),
        name=b"ALGit",
        group_id=group_id,
        mailbox=mailbox_key,
    )
    created = chain.submit(owner, [(mailbox.address, 0, create_note, "0x03-create")])
    rows += created
    create_event = AdminEvent(
        note=create_note,
        sender=owner.pubkey(),
        tx_id=txid_raw(created[0].txid),
        round=created[0].round,
        offset=0,
    )
    reduced = reduce_admin([create_event])
    if reduced.rejected or reduced.state is None:
        raise RuntimeError(f"create rejected: {reduced.rejected}")
    add_note = draft_admin(reduced.state, OP_ADD_MEMBER, owner.pubkey(), subject=member.pubkey())
    # The create round is already confirmed. The add is a new payment, so it
    # cannot share that round. status_after_block waits for an idle LocalNet
    # to cut a block on its own, and the SDK's 30s request timeout fires first.
    added = chain.submit(owner, [(mailbox.address, 0, add_note, "0x03-add")])
    rows += added
    if added[0].round <= created[0].round:
        raise RuntimeError("add-member landed in the create round; offset would be ambiguous")
    add_event = AdminEvent(
        note=add_note,
        sender=owner.pubkey(),
        tx_id=txid_raw(added[0].txid),
        round=added[0].round,
        offset=0,
    )
    reduced = reduce_admin([create_event, add_event])
    if reduced.rejected or reduced.state is None:
        raise RuntimeError(f"add rejected: {reduced.rejected}")
    if not delivery_authorized(reduced.accepted, txid_raw(added[0].txid), owner.pubkey(), member.pubkey(), reduced.state.epoch):
        raise RuntimeError("delivery of the group key is not authorized")
    delivery = seal_group_key_delivery(
        owner_session,
        reduced.state.epoch,
        group_id,
        mailbox_key,
        group_key,
        txid_raw(added[0].txid),
    )
    if len(delivery) != 227:
        raise RuntimeError(f"0x06 is {len(delivery)} bytes")
    rows += chain.submit(owner, [(member.address, 0, delivery, "0x06")])
    opened = open_group_key_delivery(delivery, member_session)
    if opened.group_key != group_key:
        raise RuntimeError("member opened a different group key")
    try:
        open_group_key_delivery(delivery, owner_session)
        # owner session can open the AEAD because it holds the same session key.
        # Authorization still requires the recipient to be the member. The bytes open.
        owner_can_open_delivery = True
    except PQError:
        owner_can_open_delivery = False
    try:
        fake = accept_pq_session(handshake, outsider.x_private, outsider.x_public, outsider.kem)
        open_group_key_delivery(delivery, fake)
        outsider_delivery = "opened"
    except PQError as exc:
        outsider_delivery = str(exc)

    ping = seal_private(b"ping", group_key, group_id, 1, 0, owner.pubkey())
    duplicate = seal_private(b"duplicate-counter", group_key, group_id, 1, 0, owner.pubkey())
    rows += chain.submit(owner, [(mailbox.address, 0, ping, "0x07-ping")])
    rows += chain.submit(owner, [(mailbox.address, 0, duplicate, "0x07-duplicate-counter")])
    first = open_group_message(ping, group_key, owner.pubkey(), [])
    try:
        open_group_message(duplicate, group_key, owner.pubkey(), [(first.epoch, first.counter)])
        duplicate_result = "opened"
    except PQError as exc:
        duplicate_result = str(exc)
    try:
        open_group_message(ping, os.urandom(32), owner.pubkey(), [])
        wrong_key = "opened"
    except PQError as exc:
        wrong_key = str(exc)

    return {
        "mailbox": mailbox.address,
        "group_id": group_id.hex(),
        "group_key": group_key,
        "group_id_bytes": group_id,
        "counter": 1,
        "rows": rows,
        "summary": summarize_sent(rows),
        "outsider_handshake": outsider_handshake,
        "outsider_0x05": outsider_message,
        "outsider_0x06": outsider_delivery,
        "wrong_group_key": wrong_key,
        "duplicate_counter": duplicate_result,
        "owner_session_opens_delivery": owner_can_open_delivery,
        "member_opened_0x05": session_text,
        "handshake_bytes": len(handshake),
        "delivery_bytes": len(delivery),
        "announce_bytes": len(announce_owner),
    }


def push_plan(
    chain: Chain,
    sender: Party,
    mailbox: str,
    plan: Plan,
    group_key: bytes | None = None,
    group_id: bytes | None = None,
    counter: int = 0,
) -> tuple[list[Sent], int, float]:
    plain = plan.notes()
    labels = labels_for(plan)
    if len(labels) != len(plain):
        raise RuntimeError(f"labels {len(labels)} != notes {len(plain)}")
    started = time.perf_counter()
    if plan.private:
        if group_key is None or group_id is None:
            raise RuntimeError("private plan needs a group")
        items, counter = private_items(plain, labels, mailbox, group_key, group_id, sender.pubkey(), counter)
    else:
        items = [(mailbox, 0, note, label) for note, label in zip(plain, labels)]
    sealed = time.perf_counter()
    print(
        f"{plan.name}: {len(items)} notes, seal {sealed - started:.2f}s, payload {plan.payload_bytes} bytes",
        flush=True,
    )
    rows = chain.submit_all(sender, items) if items else []
    return rows, counter, time.perf_counter() - started


def readback_private(
    chain: Chain,
    rows: list[Sent],
    mailbox: str,
    group_key: bytes,
    sender_address: str,
    sender_pubkey: bytes,
) -> tuple[list[dict], list[str], dict]:
    fetched = chain.block_notes([row.round for row in rows], {mailbox})
    records = []
    tx_by_note = {row.note: row.txid for row in rows if row.note}
    seen = 0
    for rnd, offset, snd, receiver, note, fee in fetched:
        if receiver != mailbox or snd != sender_address or len(note) < 2 or note[1] != 0x07:
            continue
        seen += 1
        records.append((rnd, offset, tx_by_note.get(note, ""), note))
        if fee < fee_for_note(len(note)):
            raise RuntimeError(f"block fee {fee} is under the protocol fee for {len(note)} bytes")
    frames, rejected = frames_from_private(records, group_key, sender_pubkey)
    return frames, rejected, {"fetched_0x07": seen, "submitted_rows": len(rows)}


def readback_public(chain: Chain, rows: list[Sent], mailbox: str) -> tuple[list[dict], dict]:
    fetched = chain.block_notes([row.round for row in rows], {mailbox})
    records = []
    for rnd, offset, _snd, receiver, note, fee in fetched:
        if receiver != mailbox or not note.startswith(MAGIC):
            continue
        records.append((rnd, offset, note))
        if fee < fee_for_note(len(note)):
            raise RuntimeError(f"block fee {fee} is under the protocol fee for {len(note)} bytes")
    frames = frames_from_public(records)
    return frames, {"fetched_algt": len(records), "submitted": len(rows)}


def marker_visible(rows: list[Sent], marker: bytes) -> int:
    return sum(1 for row in rows if marker in row.note)


def compare_checkout(source: str, git_dir: str, ref: str, work: Path) -> str:
    if work.exists():
        shutil.rmtree(work)
    work.mkdir(parents=True)
    subprocess.check_call(["git", "--git-dir", git_dir, "--work-tree", str(work), "checkout", "-q", "-f", ref])
    src_oid = git(source, "rev-parse", ref).decode().strip()
    dst_oid = subprocess.check_output(["git", "--git-dir", git_dir, "rev-parse", ref], text=True).strip()
    if src_oid != dst_oid:
        return f"tip mismatch {src_oid} != {dst_oid}"
    diff = subprocess.run(["diff", "-rq", source, str(work)], stdout=subprocess.PIPE, text=True)
    # The source checkout contains .git and possibly untracked measurement files.
    lines = [
        line
        for line in diff.stdout.splitlines()
        if "/.git" not in line and not line.endswith(".git") and "Only in " + source not in line
    ]
    return "clean" if not lines else "\n".join(lines[:20])


def forge_notes(chain: Chain, owner: Party, mailbox: str, group_key: bytes, group_id: bytes, sender: bytes, counter: int, head: str) -> tuple[list[Sent], int]:
    documents = [
        (
            KIND_PULL,
            json.dumps(
                {
                    "title": "Store the repository on the mailbox",
                    "body": "One pull request note. The head commit is already on this mailbox.",
                    "base": "refs/heads/main",
                    "head": head,
                    "state": "open",
                }
            ).encode(),
            "pull",
        ),
        (
            KIND_ISSUE,
            json.dumps(
                {
                    "title": "Clone is a full mailbox scan",
                    "body": "An issue note. Comments would be further notes on this same mailbox.",
                    "state": "open",
                }
            ).encode(),
            "issue",
        ),
        (
            KIND_CI,
            json.dumps(
                {
                    "name": "test",
                    "sha": head,
                    "state": "success",
                    "description": "Status only. The log is a separate note.",
                }
            ).encode(),
            "ci",
        ),
        (KIND_LOG, b"ci-log " + os.urandom(12000), "ci-log"),
    ]
    items = []
    for kind, payload, label in documents:
        plain_notes = chunk_payload(kind, bytes.fromhex(head), ZERO_OID, payload, PRIVATE_CHUNK)
        for index, plain in enumerate(plain_notes):
            note = seal_private(plain, group_key, group_id, 1, counter, sender)
            items.append((mailbox, 0, note, f"{label}:{index}"))
            counter += 1
    rows = chain.submit_all(owner, items)
    return rows, counter


def phase_algochat(chain: Chain, evidence: Path) -> dict:
    source = "/Users/leif/Development/_CorvidLabs/algochat"
    rev = ["--remotes=origin"]
    print("planning algochat", flush=True)
    started = time.perf_counter()
    packed = pack_size(source, rev)
    objects = load_objects(source, rev)
    commits = commits_topo(source, rev)
    plans = {}
    for model in ("objects", "deltas"):
        for private in (False, True):
            pieces, skipped = plan_history(source, objects, commits, model, set())
            for refname, oid in ref_map(source):
                pieces.append(Piece(KIND_REF, oid, "", refname.encode(), "ref"))
            plan = Plan(
                f"algochat-{model}-{'private' if private else 'public'}",
                model,
                private,
                pieces,
                skipped,
                len(objects),
                sum(len(piece.payload) for piece in pieces),
            )
            plans[(model, private)] = plan
            info = plan_fee(plan)
            print(
                f"  plan {plan.name}: notes {info['notes']} fee {info['fee_microalgo']} payload {info['payload_bytes']}",
                flush=True,
            )
    print(f"planning took {time.perf_counter() - started:.1f}s, pack {packed} bytes", flush=True)

    work = "/tmp/algit-algochat-work"
    clone_work(source, work)
    git(work, "checkout", "-q", "-B", "measure", "origin/main")
    readme = "README.md"
    original = Path(work, readme).read_bytes()
    private_marker = b"ALGit private marker 7e1c9a4b\n"
    public_marker = b"ALGit public marker 7e1c9a4b\n"
    one_line = original + b"\n" + private_marker
    one_commit = commit_file(work, readme, one_line, "Add one private marker line")
    base_60 = os.urandom(61440)
    add_commit = commit_file(work, "payload-60kib.bin", base_60, "Add a 60 KiB file")
    replaced = os.urandom(61440)
    replace_commit = commit_file(work, "payload-60kib.bin", replaced, "Replace the 60 KiB file")
    # A public clone gets its own one-line marker so the raw note can be searched.
    public_work = "/tmp/algit-algochat-public"
    clone_work(source, public_work)
    git(public_work, "checkout", "-q", "-B", "measure", "origin/main")
    public_commit = commit_file(
        public_work,
        readme,
        Path(public_work, readme).read_bytes() + b"\n" + public_marker,
        "Add one public marker line",
    )
    public_base = os.urandom(61440)
    public_add = commit_file(public_work, "payload-60kib.bin", public_base, "Add a 60 KiB file")
    public_replace = commit_file(public_work, "payload-60kib.bin", os.urandom(61440), "Replace the 60 KiB file")

    owner = Party.generate()
    member = Party.generate()
    outsider = Party.generate()
    dispenser_key, dispenser_addr = chain.dispenser()
    dispenser = Party.__new__(Party)
    # Fund from the dispenser with its own key pair shape.
    class Signer:
        def __init__(self, private_key: str, address: str) -> None:
            self.private_key = private_key
            self.address = address

        def pubkey(self) -> bytes:
            return encoding.decode_address(self.address)

    funder = Signer(dispenser_key, dispenser_addr)
    print(f"funding writer from {dispenser_addr}", flush=True)
    # Reuse submit by wrapping the dispenser as a Party-like object.
    owner_fund = transaction.PaymentTxn(
        funder.address,
        transaction.SuggestedParams(1000, chain.params().first, chain.params().last, chain.params().gh, chain.params().gen, True, chain.params().consensus_version, 1000),
        owner.address,
        80_000_000,
    )
    chain.algod.send_transaction(owner_fund.sign(funder.private_key))
    transaction.wait_for_confirmation(chain.algod, owner_fund.get_txid(), 40)
    # Member and outsider are funded inside setup, but the owner must already exist.
    # The fund above creates the owner. Member is funded by the owner in setup.

    room = setup_room(chain, owner, member, outsider)
    write_jsonl(evidence / "room-setup.jsonl", room["rows"])

    results = {
        "pack_bytes": packed,
        "object_census": {
            kind: sum(1 for item in objects.values() if item[0] == kind) for kind in ("blob", "tree", "commit", "tag")
        },
        "inflated_bytes": sum(len(canonical(kind, content)) for kind, content in objects.values()),
        "commits": len(commits),
        "plan_seconds": time.perf_counter() - started,
        "plans": {f"{model}-{'private' if private else 'public'}": plan_fee(plan) for (model, private), plan in plans.items()},
        "room": {key: value for key, value in room.items() if key not in {"rows", "group_key", "group_id_bytes"}},
    }
    results["room"]["group_key_sha256"] = hashlib.sha256(room["group_key"]).hexdigest()

    scenarios = {}
    # Private model 1 import and edits.
    for model, worktree, commits_for_edit in (
        ("objects", work, (one_commit, add_commit, replace_commit, private_marker)),
        ("deltas", work, (one_commit, add_commit, replace_commit, private_marker)),
    ):
        plan = plans[(model, True)]
        # The precomputed plan was built from origin objects only. Edits are separate.
        rows, counter, elapsed = push_plan(
            chain,
            owner,
            room["mailbox"],
            plan,
            room["group_key"],
            room["group_id_bytes"],
            room["counter"],
        )
        room["counter"] = counter
        write_jsonl(evidence / f"algochat-{model}-private-import.jsonl", rows)
        print(f"readback {model}", flush=True)
        read_started = time.perf_counter()
        frames, rejected, fetch_info = readback_private(
            chain, rows, room["mailbox"], room["group_key"], owner.pubkey()
        )
        rebuilt = materialize(frames, evidence / f"rebuild-{model}")
        read_elapsed = time.perf_counter() - read_started
        have = have_oids(plan)
        edit_names = ("one-line", "add-60kib", "replace-60kib")
        edit_rows = {}
        parent_have = set(have)
        for label, commit in zip(edit_names, commits_for_edit[:3]):
            edit_plan = incremental_plan(
                f"{model}-{label}",
                worktree,
                commit,
                model,
                True,
                parent_have,
                "refs/heads/measure",
            )
            sent, counter, edit_elapsed = push_plan(
                chain,
                owner,
                room["mailbox"],
                edit_plan,
                room["group_key"],
                room["group_id_bytes"],
                room["counter"],
            )
            room["counter"] = counter
            parent_have |= have_oids(edit_plan)
            write_jsonl(evidence / f"algochat-{model}-private-{label}.jsonl", sent)
            edit_rows[label] = {
                "push": summarize_sent(sent),
                "seconds": edit_elapsed,
                "plan": plan_fee(edit_plan),
                "marker_hits_in_notes": marker_visible(sent, private_marker),
            }
            rows.extend(sent)
        # Second push of the imported oids must send no object notes.
        again = incremental_plan(
            f"{model}-dedup",
            source,
            git(source, "rev-parse", "origin/main").decode().strip(),
            model,
            True,
            parent_have,
            "refs/heads/main",
        )
        object_notes = [piece for piece in again.pieces if piece.kind in {KIND_OBJECT, KIND_DELTA}]
        dedup_sent, counter, _elapsed = push_plan(
            chain,
            owner,
            room["mailbox"],
            Plan(again.name, model, True, [piece for piece in again.pieces if piece.kind == KIND_REF], again.skipped_oids, again.object_count, 0),
            room["group_key"],
            room["group_id_bytes"],
            room["counter"],
        )
        room["counter"] = counter
        scenarios[model] = {
            "import": summarize_sent(rows[: len(rows) - sum(len(json.loads(line)) for line in [])] if False else [row for row in rows if row.label.startswith(("object", "delta", "ref", "tree", "commit", "blob", "tag")) or True]),
            "import_push": summarize_sent(
                [
                    row
                    for row in rows
                    if not row.label.startswith("one-line")
                    and not row.label.startswith("add-60")
                    and not row.label.startswith("replace-")
                    and not row.label.startswith("ref:measure")
                ]
            ),
            "seconds": elapsed,
            "read_seconds": read_elapsed,
            "read": fetch_info,
            "rejected_counters": rejected,
            "fsck_code": rebuilt["fsck_code"],
            "fsck": rebuilt["fsck"][:500],
            "objects_rebuilt": rebuilt["objects"],
            "refs_rebuilt": len(rebuilt["refs"]),
            "main": rebuilt["refs"].get("refs/heads/main"),
            "edits": edit_rows,
            "dedup_object_notes": len(object_notes),
            "dedup_ref": summarize_sent(dedup_sent),
            "marker_hits_in_import_notes": marker_visible(rows, private_marker),
        }
        # The import summary above is messy because rows includes edits. Recompute from the jsonl.
        import_rows = [
            Sent(**{**json.loads(line), "note": b""})
            for line in (evidence / f"algochat-{model}-private-import.jsonl").read_text().splitlines()
        ]
        scenarios[model]["import_push"] = summarize_sent(import_rows)
        print(f"{model} fsck {rebuilt['fsck_code']} objects {rebuilt['objects']}", flush=True)

    # One private mailbox was used for BOTH models above, which mixes them.
    # That is wrong. Each model needs its own mailbox. The loop above reused one room.
    # This is fixed by raising if we got here... we need separate rooms.
    # The function is rewritten below if this assertion fires during development.
    results["scenarios_mixed_mailbox"] = scenarios
    return results


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--phase", default="plan", choices=["self-test", "plan", "probe", "algochat", "large"])
    parser.add_argument("--repo", default="/Users/leif/Development/_CorvidLabs/site")
    args = parser.parse_args()
    self_test_delta()
    print("self-test ok", flush=True)
    if args.phase == "self-test":
        return
    EVIDENCE.mkdir(parents=True, exist_ok=True)
    if args.phase == "plan":
        disk = github_disk()
        (EVIDENCE / "github-disk.json").write_text(json.dumps(disk, indent=2))
        print(json.dumps(disk, indent=2))
        source = "/Users/leif/Development/_CorvidLabs/algochat"
        packed = pack_size(source, origin_revs())
        report = {"pack_bytes": packed, "py_algorand_sdk": SDK_VERSION}
        for model in ("objects", "deltas"):
            for private in (False, True):
                plan, census = build_origin_plan(source, model, private)
                report["census"] = census
                info = plan_fee(plan)
                report[f"{model}-{'private' if private else 'public'}"] = info
                print(model, "private" if private else "public", info["notes"], info["fee_microalgo"], flush=True)
        (EVIDENCE / "algochat-plan.json").write_text(json.dumps(report, indent=2))
        return
    chain = Chain()
    print("localnet round", chain.status_round(), flush=True)
    if args.phase == "probe":
        owner = Party.generate()
        sink = Party.generate()
        key, addr = chain.dispenser()
        base = chain.params()
        fund = transaction.PaymentTxn(
            addr,
            transaction.SuggestedParams(1000, base.first, base.last, base.gh, base.gen, True, base.consensus_version, 1000),
            owner.address,
            5_000_000,
        )
        chain.algod.send_transaction(fund.sign(key))
        transaction.wait_for_confirmation(chain.algod, fund.get_txid(), 40)
        chain.submit(owner, [(sink.address, 200_000, b"", "fund-sink")])
        report = run_probe(chain, owner, sink.address)
        (EVIDENCE / "fee-probe.json").write_text(json.dumps(report, indent=2))
        print(json.dumps(report, indent=2))
        return
    if args.phase == "algochat":
        # Implemented as a clean two-mailbox run in phase_algochat_clean.
        report = phase_algochat_clean(chain)
        (EVIDENCE / "algochat-localnet.json").write_text(json.dumps(report, indent=2, default=str))
        print(json.dumps({key: report[key] for key in report if key != "debug"}, indent=2, default=str)[:4000])
        return
    if args.phase == "large":
        report = phase_large(chain, args.repo)
        (EVIDENCE / "large-localnet.json").write_text(json.dumps(report, indent=2, default=str))
        print(json.dumps(report, indent=2, default=str)[:4000])


def fund_owner(chain: Chain, owner: Party, amount: int) -> str:
    key, addr = chain.dispenser()
    base = chain.params(force=True)
    fund = transaction.PaymentTxn(
        addr,
        transaction.SuggestedParams(1000, base.first, base.last, base.gh, base.gen, True, base.consensus_version, 1000),
        owner.address,
        amount,
    )
    chain.algod.send_transaction(fund.sign(key))
    info = transaction.wait_for_confirmation(chain.algod, fund.get_txid(), 40)
    return f"{fund.get_txid()} round {info['confirmed-round']}"


def import_and_edits(
    chain: Chain,
    evidence: Path,
    source: str,
    model: str,
    private: bool,
    origin_plan: Plan,
    work: str,
    commits: tuple[str, str, str],
    marker: bytes,
) -> dict:
    owner = Party.generate()
    member = Party.generate()
    outsider = Party.generate()
    print(fund_owner(chain, owner, 60_000_000), flush=True)
    room = None
    mailbox = ""
    counter = 0
    group_key = None
    group_id = None
    prefix = f"algochat-{model}-{'private' if private else 'public'}"
    if private:
        room = setup_room(chain, owner, member, outsider)
        write_jsonl(evidence / f"{prefix}-setup.jsonl", room["rows"])
        mailbox = room["mailbox"]
        counter = room["counter"]
        group_key = room["group_key"]
        group_id = room["group_id_bytes"]
        (evidence / f"{prefix}-room.json").write_text(
            json.dumps(
                {
                    "mailbox": mailbox,
                    "owner": owner.address,
                    "owner_pubkey": owner.pubkey().hex(),
                    "group_id": group_id.hex(),
                    "group_key": group_key.hex(),
                }
            )
        )
    else:
        box = Party.generate()
        funded = chain.submit(owner, [(box.address, 100_000, b"", "fund-mailbox")])
        mailbox = box.address
        write_jsonl(evidence / f"{prefix}-setup.jsonl", funded)
        room = {"rows": funded, "summary": summarize_sent(funded), "mailbox": mailbox}
    rows, counter, elapsed = push_plan(chain, owner, mailbox, origin_plan, group_key, group_id, counter)
    write_jsonl(evidence / f"{prefix}-import.jsonl", rows)
    print("readback", prefix, flush=True)
    read_started = time.perf_counter()
    if private:
        assert rows and rows[0].note[:2] == b"\x02\x07"
        assert rows[0].note[2:34] == group_id
        frames, rejected, fetch_info = readback_private(
            chain, room["rows"] + rows, mailbox, group_key, owner.address, owner.pubkey()
        )
    else:
        assert rows and rows[0].note.startswith(MAGIC)
        frames, fetch_info = readback_public(chain, rows, mailbox)
        rejected = []
    rebuilt = materialize(frames, evidence / f"rebuild-{prefix}")
    expected_main = git(source, "rev-parse", "origin/main").decode().strip()
    if rebuilt["fsck_code"] != 0:
        raise RuntimeError(rebuilt["fsck"])
    if rebuilt["refs"].get("refs/heads/main") != expected_main:
        raise RuntimeError(f"main {rebuilt['refs'].get('refs/heads/main')} != {expected_main}")
    if rebuilt["objects"] != origin_plan.object_count:
        raise RuntimeError(f"rebuilt {rebuilt['objects']} objects, plan has {origin_plan.object_count}")
    read_elapsed = time.perf_counter() - read_started
    have = have_oids(origin_plan)
    edits = {}
    names = ("one-line", "add-60kib", "replace-60kib")
    for label, commit in zip(names, commits):
        edit_plan = incremental_plan(f"{prefix}-{label}", work, commit, model, private, have, "refs/heads/measure")
        sent, counter, edit_elapsed = push_plan(chain, owner, mailbox, edit_plan, group_key, group_id, counter)
        have |= have_oids(edit_plan)
        write_jsonl(evidence / f"{prefix}-{label}.jsonl", sent)
        hits = marker_visible(sent, marker)
        if private and hits:
            raise RuntimeError(f"{label} leaked the marker into a raw note")
        if not private and label == "one-line" and hits == 0:
            raise RuntimeError("public one-line note does not contain the marker")
        checked = verify_edit_frames(chain, sent, mailbox, private, group_key, owner, work)
        edits[label] = {
            "push": summarize_sent(sent),
            "seconds": round(edit_elapsed, 3),
            "plan": plan_fee(edit_plan),
            "marker_in_raw_notes": hits,
            "chain_objects_checked": checked,
        }
    dedup = incremental_plan(
        f"{prefix}-dedup",
        source,
        git(source, "rev-parse", "origin/main").decode().strip(),
        model,
        private,
        have,
        "refs/heads/main",
    )
    dedup_objects = [piece for piece in dedup.pieces if piece.kind in {KIND_OBJECT, KIND_DELTA}]
    ref_only = Plan(dedup.name, model, private, [piece for piece in dedup.pieces if piece.kind == KIND_REF], dedup.skipped_oids, dedup.object_count, 0)
    dedup_sent, counter, _elapsed = push_plan(chain, owner, mailbox, ref_only, group_key, group_id, counter)
    write_jsonl(evidence / f"{prefix}-dedup.jsonl", dedup_sent)
    forge = None
    if private and model == "objects":
        head = git(source, "rev-parse", "origin/main").decode().strip()
        forge_rows, counter = forge_notes(chain, owner, mailbox, group_key, group_id, owner.pubkey(), counter, head)
        write_jsonl(evidence / f"{prefix}-forge.jsonl", forge_rows)
        forge = summarize_sent(forge_rows)
        forge["labels"] = [row.label for row in forge_rows]
        forge["txids"] = [row.txid for row in forge_rows]
    return {
        "mailbox": mailbox,
        "owner": owner.address,
        "member": member.address,
        "outsider": outsider.address,
        "setup": room["summary"] if isinstance(room, dict) and "summary" in room else summarize_sent(room["rows"]),
        "setup_detail": {
            key: room[key]
            for key in room
            if key not in {"rows", "group_key", "group_id_bytes"} and room.get("group_key") is not None
        }
        if private
        else {"mailbox_fund": summarize_sent(room["rows"])},
        "import": summarize_sent(rows),
        "import_seconds": round(elapsed, 3),
        "read_seconds": round(read_elapsed, 3),
        "fetch": fetch_info,
        "rejected": rejected[:10],
        "rejected_count": len(rejected),
        "fsck_code": rebuilt["fsck_code"],
        "fsck": rebuilt["fsck"][:800],
        "objects_rebuilt": rebuilt["objects"],
        "ref_count": len(rebuilt["refs"]),
        "main": rebuilt["refs"].get("refs/heads/main"),
        "expected_main": git(source, "rev-parse", "origin/main").decode().strip(),
        "marker_in_import_notes": marker_visible(rows, marker),
        "edits": edits,
        "dedup_object_pieces": len(dedup_objects),
        "dedup_ref": summarize_sent(dedup_sent),
        "forge": forge,
        "counter_end": counter,
    }


def origin_revs() -> list[str]:
    return ["--remotes=origin", "--tags"]


def build_origin_plan(source: str, model: str, private: bool) -> tuple[Plan, dict]:
    rev = origin_revs()
    objects = load_objects(source, rev)
    commits = commits_topo(source, rev)
    pieces, skipped = plan_history(source, objects, commits, model, set())
    covered = {piece.oid for piece in pieces if piece.kind in {KIND_OBJECT, KIND_DELTA}}
    missing = [oid for oid in objects if oid not in covered]
    if missing:
        raise RuntimeError(f"{model} plan dropped {len(missing)} objects, first {missing[0]}")
    for refname, oid in ref_map(source):
        if oid not in objects:
            continue
        pieces.append(Piece(KIND_REF, oid, "", refname.encode(), "ref"))
    plan = Plan(
        f"algochat-{model}-{'private' if private else 'public'}",
        model,
        private,
        pieces,
        skipped,
        len(objects),
        sum(len(piece.payload) for piece in pieces),
    )
    census = {
        "objects": len(objects),
        "commits": len(commits),
        "by_type": {
            kind: {
                "count": sum(1 for item in objects.values() if item[0] == kind),
                "content_bytes": sum(len(item[1]) for item in objects.values() if item[0] == kind),
            }
            for kind in ("blob", "tree", "commit", "tag")
        },
        "canonical_bytes": sum(len(canonical(kind, content)) for kind, content in objects.values()),
    }
    return plan, census


def prepare_edits(source: str, work: str, marker: bytes) -> tuple[str, str, str]:
    clone_work(source, work)
    git(work, "checkout", "-q", "-B", "measure", "origin/main")
    one = commit_file(work, "README.md", Path(work, "README.md").read_bytes() + b"\n" + marker, "Add one marker line")
    added = commit_file(work, "payload-60kib.bin", os.urandom(61440), "Add a 60 KiB file")
    replaced = commit_file(work, "payload-60kib.bin", os.urandom(61440), "Replace the 60 KiB file")
    return one, added, replaced


def phase_algochat_clean(chain: Chain) -> dict:
    source = "/Users/leif/Development/_CorvidLabs/algochat"
    print("pack and plans", flush=True)
    packed = pack_size(source, origin_revs())
    disk = github_disk()
    (EVIDENCE / "github-disk.json").write_text(json.dumps(disk, indent=2))
    private_marker = b"ALGit private marker 7e1c9a4b\n"
    public_marker = b"ALGit public marker 7e1c9a4b\n"
    report: dict = {"pack_bytes": packed, "github": disk, "runs": {}}
    # Private objects, private deltas, public objects. Public deltas are fee-identical
    # to the private delta plan minus the 70-byte envelope, which plan_fee already computes.
    for model, private, marker in (
        ("objects", True, private_marker),
        ("deltas", True, private_marker),
        ("objects", False, public_marker),
    ):
        print(f"=== {model} {'private' if private else 'public'} ===", flush=True)
        plan, census = build_origin_plan(source, model, private)
        report["census"] = census
        report["plans"] = report.get("plans", {})
        report["plans"][plan.name] = plan_fee(plan)
        # Also record the sibling visibility's fee without a second history walk.
        sibling = Plan(plan.name + "-fee", model, not private, plan.pieces, plan.skipped_oids, plan.object_count, plan.payload_bytes)
        report["plans"][f"{model}-{'public' if private else 'private'}-from-same-pieces"] = plan_fee(sibling)
        work = f"/tmp/algit-{model}-{'priv' if private else 'pub'}"
        commits = prepare_edits(source, work, marker)
        report["runs"][plan.name] = import_and_edits(
            chain, EVIDENCE, source, model, private, plan, work, commits, marker
        )
    # Public delta fees were computed. Do the public delta edits on chain too if the
    # object import was cheap: the caller decides by invoking this once.
    # A public delta import is included when ALGIR_PUBLIC_DELTAS=1.
    if os.environ.get("ALGIT_PUBLIC_DELTAS") == "1":
        plan, _census = build_origin_plan(source, "deltas", False)
        work = "/tmp/algit-deltas-pub"
        commits = prepare_edits(source, work, public_marker)
        report["runs"][plan.name] = import_and_edits(
            chain, EVIDENCE, source, "deltas", False, plan, work, commits, public_marker
        )
    return report


def phase_large(chain: Chain, repo: str) -> dict:
    print("large plan", repo, flush=True)
    try:
        git(repo, "rev-parse", "--verify", "refs/remotes/origin/HEAD")
        rev = origin_revs()
    except RuntimeError:
        rev = ["--all"]
    started = time.perf_counter()
    objects = load_objects(repo, rev)
    commits = commits_topo(repo, rev)
    print(f"loaded {len(objects)} objects, {len(commits)} commits in {time.perf_counter() - started:.1f}s", flush=True)
    report: dict = {
        "repo": repo,
        "objects": len(objects),
        "commits": len(commits),
        "canonical_bytes": sum(len(canonical(kind, content)) for kind, content in objects.values()),
        "plans": {},
    }
    pieces_by_model = {}
    for model in ("objects", "deltas"):
        t0 = time.perf_counter()
        pieces, skipped = plan_history(repo, objects, commits, model, set())
        for refname, oid in ref_map(repo):
            pieces.append(Piece(KIND_REF, oid, "", refname.encode(), "ref"))
        pieces_by_model[model] = pieces
        for private in (False, True):
            plan = Plan(model, model, private, pieces, skipped, len(objects), sum(len(piece.payload) for piece in pieces))
            report["plans"][f"{model}-{'private' if private else 'public'}"] = plan_fee(plan)
            report["plans"][f"{model}-{'private' if private else 'public'}"]["plan_seconds"] = round(time.perf_counter() - t0, 3)
        print(model, "planned", report["plans"][f"{model}-public"]["notes"], "public notes", flush=True)
    # Chain the public object model. It is the larger write and needs no group seal.
    plan = Plan("large-objects-public", "objects", False, pieces_by_model["objects"], 0, len(objects), sum(len(p.payload) for p in pieces_by_model["objects"]))
    owner = Party.generate()
    box = Party.generate()
    print(fund_owner(chain, owner, 800_000_000), flush=True)
    chain.submit(owner, [(box.address, 100_000, b"", "fund-mailbox")])
    rows, _counter, elapsed = push_plan(chain, owner, box.address, plan)
    write_jsonl(EVIDENCE / "large-objects-public.jsonl", rows)
    # Read back every note via the blocks the payments landed in, then check oids.
    print("large readback", flush=True)
    t0 = time.perf_counter()
    frames, fetch_info = readback_public(chain, rows, box.address)
    # Verify oids without writing a 1 GB loose repo if memory is already holding it.
    checked = 0
    for frame_item in frames:
        if frame_item["kind"] == KIND_OBJECT and frame_item["count"] == 1:
            payload = frame_item["payload"]
            if sha1(payload) != frame_item["oid"]:
                raise RuntimeError("large single-chunk oid mismatch")
            checked += 1
    # Full materialize is the real clone. Do it.
    rebuilt = materialize(frames, EVIDENCE / "rebuild-large")
    report["chain"] = {
        "mailbox": box.address,
        "owner": owner.address,
        "import": summarize_sent(rows),
        "seconds": round(elapsed, 3),
        "read_seconds": round(time.perf_counter() - t0, 3),
        "fetch": fetch_info,
        "single_chunk_checked": checked,
        "fsck_code": rebuilt["fsck_code"],
        "fsck": rebuilt["fsck"][:800],
        "objects_rebuilt": rebuilt["objects"],
        "refs": len(rebuilt["refs"]),
    }
    return report


if __name__ == "__main__":
    main()
