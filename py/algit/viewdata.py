"""Commits, files, and receipt facts for the local page."""

from __future__ import annotations

import subprocess

__all__ = ["blob_sizes", "file_tree", "commit_list", "overview"]


def _git(root: str, *args: str) -> str:
    result = subprocess.run(
        ["git", "-C", root, *args],
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
