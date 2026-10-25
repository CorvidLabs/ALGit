"""Overview of a repository: commits, the file tree, and the receipt."""

from __future__ import annotations

import os
import subprocess
import sys
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "py"))

from algit.viewdata import blob_sizes, commit_list, file_tree, overview  # noqa: E402

GIT_ENV = {
    **os.environ,
    "GIT_AUTHOR_NAME": "ALGit",
    "GIT_AUTHOR_EMAIL": "algit@example.invalid",
    "GIT_COMMITTER_NAME": "ALGit",
    "GIT_COMMITTER_EMAIL": "algit@example.invalid",
}


def git(repo: str, *args: str) -> str:
    result = subprocess.run(
        ["git", "-C", repo, *args],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        env=GIT_ENV,
        check=False,
    )
    if result.returncode != 0:
        raise RuntimeError(result.stderr)
    return result.stdout.strip()


def make_repo(root: Path) -> Path:
    repo = root / "src"
    repo.mkdir()
    subprocess.check_call(["git", "init", "-q", "-b", "main", str(repo)], env=GIT_ENV)
    git(str(repo), "config", "core.autocrlf", "false")
    return repo


class ViewData(unittest.TestCase):
    def test_overview_bytes_tree_commits_and_account(self) -> None:
        with TemporaryDirectory() as tmp:
            repo = make_repo(Path(tmp))
            readme = repo / "README.md"
            source = repo / "src" / "a.txt"
            source.parent.mkdir()
            readme.write_bytes(b"hello\n")
            source.write_bytes(b"a\n")
            git(str(repo), "add", "README.md", "src/a.txt")
            git(str(repo), "commit", "-q", "-m", "start")
            readme.write_bytes(b"hello again\n")
            git(str(repo), "add", "README.md")
            git(str(repo), "commit", "-q", "-m", "readme")

            data = overview(
                str(repo),
                {
                    "mailbox": "ADDR",
                    "network": "localnet",
                    "microalgo": 1_500_000,
                    "notes": 4,
                    "rounds": [3, 4],
                    "head": "abc",
                    "pinned": ["cid"],
                },
            )
            readme_size = readme.stat().st_size
            source_size = source.stat().st_size
            self.assertEqual(data["bytes"], readme_size + source_size)
            self.assertEqual(data["bytes"], sum(blob_sizes(str(repo)).values()))
            self.assertEqual(data["files"], ["README.md", "src/a.txt"])
            self.assertEqual(data["branch"], "main")
            src = next(node for node in data["tree"] if node["name"] == "src")
            self.assertEqual(set(src), {"name", "children", "bytes"})
            self.assertEqual(src["children"][0]["path"], "src/a.txt")
            self.assertEqual(src["bytes"], source_size)
            self.assertEqual([node["name"] for node in data["tree"]], ["src", "README.md"])
            commits = data["commits"]
            self.assertEqual(commits, commit_list(str(repo)))
            self.assertEqual(commits[0]["subject"], "readme")
            self.assertEqual(commits[0]["author"], "ALGit")
            self.assertIsInstance(commits[0]["at"], int)
            self.assertEqual(commits[0]["files"], 1)
            self.assertEqual(commits[1]["files"], 2)
            account = data["account"]
            self.assertEqual(account["microalgo"], 1_500_000)
            self.assertEqual(account["algo"], 1.5)
            self.assertEqual(account["notes"], 4)
            self.assertEqual(account["rounds"], 2)
            self.assertEqual(account["firstRound"], 3)
            self.assertEqual(account["lastRound"], 4)
            self.assertEqual(account["head"], "abc")
            self.assertEqual(account["pinned"], 1)

            empty = overview(str(repo), {})
            self.assertEqual(empty["mailbox"], "")
            self.assertEqual(empty["network"], "")
            self.assertIsNone(empty["account"]["algo"])
            self.assertEqual(empty["account"]["rounds"], 0)
            self.assertIsNone(empty["account"]["firstRound"])
            self.assertIsNone(empty["account"]["lastRound"])
            self.assertEqual(empty["account"]["head"], "")
            self.assertEqual(empty["account"]["pinned"], 0)
            self.assertEqual(overview(str(repo), {"pinned": 2})["account"]["pinned"], 2)

    def test_dot_directory_is_kept(self) -> None:
        with TemporaryDirectory() as tmp:
            repo = make_repo(Path(tmp))
            note = repo / ".hidden" / "note.txt"
            note.parent.mkdir()
            note.write_bytes(b"dot\n")
            git(str(repo), "add", ".hidden/note.txt")
            git(str(repo), "commit", "-q", "-m", "dot")
            sizes = blob_sizes(str(repo))
            self.assertEqual(sizes[".hidden/note.txt"], note.stat().st_size)
            tree = file_tree(sorted(sizes), sizes)
            self.assertEqual(tree[0]["name"], ".hidden")
            self.assertEqual(tree[0]["children"][0]["path"], ".hidden/note.txt")
            self.assertEqual(tree[0]["bytes"], note.stat().st_size)

    def test_file_tree_sorts_directories_before_files(self) -> None:
        tree = file_tree(
            [".github/workflows/ci.yml", ".gitignore", "src/a.txt", "README.md", "src/b.txt"],
            {
                ".github/workflows/ci.yml": 3,
                ".gitignore": 1,
                "src/a.txt": 2,
                "README.md": 5,
                "src/b.txt": 4,
            },
        )
        self.assertEqual([node["name"] for node in tree], [".github", "src", ".gitignore", "README.md"])
        self.assertNotIn("path", tree[0])
        self.assertEqual(tree[0]["bytes"], 3)
        workflows = tree[0]["children"][0]
        self.assertEqual(workflows["name"], "workflows")
        self.assertEqual(workflows["children"][0]["path"], ".github/workflows/ci.yml")
        self.assertEqual([child["name"] for child in tree[1]["children"]], ["a.txt", "b.txt"])
        self.assertEqual(tree[1]["bytes"], 6)

    def test_git_failure_raises_runtime_error(self) -> None:
        with TemporaryDirectory() as tmp:
            with self.assertRaises(RuntimeError):
                blob_sizes(tmp)
