"""Commits, files, and receipt facts for the local page."""

from __future__ import annotations

import subprocess

__all__ = [
    "blob_sizes",
    "file_tree",
    "commit_list",
    "commit_cost",
    "note_fee",
    "object_note_fees",
    "overview",
]

HEADER = 51
PUBLIC_CHUNK = 4096 - HEADER


def _git(root: str, *args: str, input_text: str | None = None) -> str:
    result = subprocess.run(
        ["git", "-C", root, *args],
        input=None if input_text is None else input_text.encode(),
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )
    if result.returncode != 0:
        detail = result.stderr.decode("utf-8", "replace").strip()
        raise RuntimeError(detail or f"git {' '.join(args)} failed")
    return result.stdout.decode("utf-8")


def blob_sizes(root: str) -> dict[str, int]:
    found: dict[str, int] = {}
    for line in _git(root, "ls-tree", "-r", "-l", "HEAD").splitlines():
        meta, sep, path = line.partition("\t")
        if not sep or not path:
            continue
        parts = meta.split()
        if len(parts) < 4:
            continue
        try:
            size = int(parts[-1])
        except ValueError:
            continue
        found[path] = size
    return found


def file_tree(paths: list[str], sizes: dict[str, int]) -> list[dict]:
    """Nested folders. A directory is `{name, children, bytes}`; a file is `{name, path, bytes}`."""
    root: dict = {"children": []}

    def directory(node: dict, name: str) -> dict:
        for child in node["children"]:
            if "children" in child and child["name"] == name:
                return child
        made = {"name": name, "children": []}
        node["children"].append(made)
        return made

    for path in paths:
        if not path:
            continue
        parts = path.split("/")
        node = root
        for name in parts[:-1]:
            node = directory(node, name)
        node["children"].append({"name": parts[-1], "path": path, "bytes": int(sizes.get(path, 0))})
    _sort_tree(root["children"])
    _roll_bytes(root)
    return root["children"]


def note_fee(note_len: int, min_fee: int = 1000) -> int:
    """MicroALGO for one note. Same integer rule as the push."""
    if note_len < 0 or note_len > 4096:
        raise ValueError(f"note length {note_len} is not legal")
    over = max(0, note_len - 1024)
    return min_fee + (over * min_fee + 9999) // 10000


def object_note_fees(kind: str, content_size: int, min_fee: int = 1000) -> tuple[int, int]:
    """Return (microalgo, note count) for one canonical git object."""
    canonical = len(f"{kind} {content_size}".encode()) + 1 + content_size
    remaining = canonical
    fees = 0
    notes = 0
    while remaining > 0:
        take = min(PUBLIC_CHUNK, remaining)
        fees += note_fee(HEADER + take, min_fee)
        notes += 1
        remaining -= take
    if notes == 0:
        fees = note_fee(HEADER, min_fee)
        notes = 1
    return fees, notes


def commit_cost(root: str, oid: str, min_fee: int = 1000) -> dict:
    """ALGO for the git objects this commit introduces. Ref notes are not included."""
    parents = _git(root, "rev-parse", f"{oid}^@").split()
    if parents:
        listed = _git(root, "rev-list", "--objects", oid, f"^{parents[0]}")
    else:
        listed = _git(root, "rev-list", "--objects", oid)
    oids = []
    seen = set()
    for line in listed.splitlines():
        item = line.split()[0]
        if item not in seen:
            seen.add(item)
            oids.append(item)
    checked = _git(root, "cat-file", "--batch-check", input_text="\n".join(oids) + "\n") if oids else ""
    micro = 0
    notes = 0
    content_bytes = 0
    objects = 0
    for line in checked.splitlines():
        parts = line.split()
        if len(parts) < 3 or parts[1] == "missing":
            continue
        kind, size_text = parts[1], parts[2]
        try:
            size = int(size_text)
        except ValueError:
            continue
        fee, count = object_note_fees(kind, size, min_fee)
        micro += fee
        notes += count
        content_bytes += size
        objects += 1
    return {"id": oid, "microalgo": micro, "notes": notes, "objects": objects, "bytes": content_bytes}


def commit_list(root: str) -> list[dict]:
    # Header, a blank line, then paths. The next header follows the last path.
    raw = _git(root, "log", "--format=%H%x1f%an%x1f%at%x1f%s", "--name-only")
    commits: list[dict] = []
    current: dict | None = None
    files = 0
    for line in raw.splitlines():
        if "\x1f" in line:
            bits = line.split("\x1f", 3)
            if len(bits) == 4:
                if current is not None:
                    current["files"] = files
                    commits.append(current)
                oid, author, stamp, subject = bits
                current = {"id": oid, "author": author, "at": int(stamp), "subject": subject}
                current.update(commit_cost(root, oid))
                files = 0
                continue
        if current is not None and line:
            files += 1
    if current is not None:
        current["files"] = files
        commits.append(current)
    return commits


def overview(root: str, receipt: dict) -> dict:
    branch = _git(root, "rev-parse", "--abbrev-ref", "HEAD").strip()
    sizes = blob_sizes(root)
    files = sorted(sizes)
    rounds = receipt.get("rounds") or []
    if isinstance(rounds, (list, tuple)) and rounds:
        round_count, first_round, last_round = len(rounds), rounds[0], rounds[-1]
    else:
        round_count, first_round, last_round = 0, None, None
    micro = receipt.get("microalgo")
    pinned = receipt.get("pinned")
    pinned_count = len(pinned) if isinstance(pinned, list) else int(pinned or 0)
    return {
        "branch": branch,
        "mailbox": receipt.get("mailbox") or "",
        "network": receipt.get("network") or "",
        "commits": commit_list(root),
        "files": files,
        "tree": file_tree(files, sizes),
        "bytes": sum(sizes.values()),
        "account": {
            "microalgo": micro,
            "algo": None if micro is None else micro / 1_000_000,
            "notes": receipt.get("notes"),
            "rounds": round_count,
            "firstRound": first_round,
            "lastRound": last_round,
            "head": receipt.get("head") or "",
            "pinned": pinned_count,
        },
    }


def _roll_bytes(node: dict) -> int:
    if "children" not in node:
        return int(node.get("bytes") or 0)
    total = 0
    for child in node["children"]:
        total += _roll_bytes(child)
    node["bytes"] = total
    return total


def _sort_tree(nodes: list[dict]) -> None:
    nodes.sort(key=lambda item: (0 if "children" in item else 1, item["name"]))
    for item in nodes:
        if "children" in item:
            _sort_tree(item["children"])
