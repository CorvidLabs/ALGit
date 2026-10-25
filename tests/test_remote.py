"""REQ-algit-1 through REQ-algit-7."""

from __future__ import annotations

import json
import os
import subprocess
import sys
import threading
import unittest
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from tempfile import TemporaryDirectory

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "py"))

from algit.command import (  # noqa: E402
    clone_mailbox,
    fee_for_note,
    main,
    materialize_frames,
    pin_heavy_blobs,
    plan_repository,
    push_localnet,
    quote_push,
    serve,
)

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


def make_repo(root: Path, files: dict[str, bytes]) -> str:
    repo = root / "src"
    repo.mkdir()
    subprocess.check_call(["git", "init", "-q", "-b", "main", str(repo)])
    for name, content in files.items():
        path = repo / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(content)
        git(str(repo), "add", name)
    git(str(repo), "commit", "-q", "-m", "start")
    return str(repo)


def localnet_up() -> bool:
    try:
        with urllib.request.urlopen("http://127.0.0.1:4001/health", timeout=2) as response:
            return response.status == 200
    except OSError:
        return False


class FeeAndPlan(unittest.TestCase):
    def test_fee_matches_the_localnet_probe(self) -> None:
        self.assertEqual(fee_for_note(4096), 1308)
        self.assertEqual(fee_for_note(1024), 1000)
        self.assertEqual(fee_for_note(1025), 1001)

    def test_plan_round_trip_fsck(self) -> None:
        # REQ-algit-1 REQ-algit-3
        with TemporaryDirectory() as tmp:
            repo = make_repo(Path(tmp), {"README.md": b"hello\n", "src/a.txt": b"a"})
            head = git(repo, "rev-parse", "HEAD")
            plan = plan_repository(repo, env={})
            frames = []
            for note in plan.notes():
                frames.append(
                    {
                        "kind": note[5],
                        "oid": note[7:27],
                        "index": int.from_bytes(note[47:49], "big"),
                        "count": int.from_bytes(note[49:51], "big"),
                        "payload": note[51:],
                    }
                )
            built = materialize_frames(frames, str(Path(tmp) / "out"))
            self.assertEqual(built["fsck_code"], 0)
            self.assertEqual(built["refs"]["refs/heads/main"], head)

    def test_checkout_keeps_a_slash_in_the_branch_name(self) -> None:
        # REQ-algit-3
        from algit.command import _checkout_work

        with TemporaryDirectory() as tmp:
            repo = make_repo(Path(tmp), {"README.md": b"hello\n"})
            git(repo, "checkout", "-q", "-b", "feature/slash")
            (Path(repo) / "extra.txt").write_text("slash\n")
            git(repo, "add", "extra.txt")
            git(repo, "commit", "-q", "-m", "slash branch")
            tip = git(repo, "rev-parse", "HEAD")
            plan = plan_repository(repo, env={})
            frames = [
                {
                    "kind": note[5],
                    "oid": note[7:27],
                    "index": int.from_bytes(note[47:49], "big"),
                    "count": int.from_bytes(note[49:51], "big"),
                    "payload": note[51:],
                }
                for note in plan.notes()
            ]
            built = materialize_frames(frames, str(Path(tmp) / "out"))
            work = str(Path(tmp) / "out" / "work")
            branch = _checkout_work(built["git_dir"], built["refs"], work)
            self.assertEqual(branch, "feature/slash")
            self.assertEqual(git(work, "rev-parse", "HEAD"), tip)
            self.assertEqual(git(work, "rev-parse", "--abbrev-ref", "HEAD"), "feature/slash")

    def test_mainnet_quote_submits_nothing(self) -> None:
        # REQ-algit-2 REQ-algit-7
        with TemporaryDirectory() as tmp:
            repo = make_repo(Path(tmp), {"README.md": b"hello\n"})
            quote = quote_push(repo, min_fee=1000, env={})
            self.assertGreater(quote["microalgo"], 0)
            self.assertEqual(quote["submitted"], 0)
            code = main(["push", "--network", "mainnet", "--repo", repo])
            self.assertEqual(code, 0)


class Pin(unittest.TestCase):
    def test_heavy_blob_uses_the_caller_jwt_and_stays_out_of_the_note(self) -> None:
        # REQ-algit-5 REQ-algit-6
        seen = {}

        class Handler(BaseHTTPRequestHandler):
            def do_POST(self) -> None:  # noqa: N802
                length = int(self.headers.get("Content-Length") or 0)
                seen["body"] = self.rfile.read(length)
                seen["authorization"] = self.headers.get("Authorization")
                payload = json.dumps({"IpfsHash": "bafytestheavy"}).encode()
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(payload)))
                self.end_headers()
                self.wfile.write(payload)

            def log_message(self, fmt: str, *args) -> None:
                return

        server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        endpoint = f"http://127.0.0.1:{server.server_address[1]}/pin"
        try:
            with TemporaryDirectory() as tmp:
                blob = b"Z" * (262_144 + 1)
                repo = make_repo(Path(tmp), {"big.bin": blob, "README.md": b"small\n"})
                with self.assertRaises(RuntimeError):
                    plan_repository(repo, env={})
                env = {"PINATA_JWT": "caller-secret", "PINATA_GATEWAY": "caller.example"}
                plan = plan_repository(repo, env=env, endpoint=endpoint)
                notes = b"".join(plan.notes())
                self.assertNotIn(blob[:80], notes)
                self.assertIn(b"ipfs://bafytestheavy", notes)
                self.assertEqual(seen["authorization"], "Bearer caller-secret")
                self.assertEqual(plan.pinned[0]["url"], "https://caller.example/ipfs/bafytestheavy")
                built = materialize_frames(
                    [
                        {
                            "kind": note[5],
                            "oid": note[7:27],
                            "index": int.from_bytes(note[47:49], "big"),
                            "count": int.from_bytes(note[49:51], "big"),
                            "payload": note[51:],
                        }
                        for note in plan.notes()
                    ],
                    str(Path(tmp) / "out"),
                )
                self.assertEqual(built["fsck_code"], 0)
        finally:
            server.shutdown()

    def test_sources_have_no_corvid_pinata_account(self) -> None:
        # REQ-algit-6
        for path in (ROOT / "py").rglob("*.py"):
            text = path.read_text()
            self.assertNotIn("eyJ", text)
            self.assertNotIn("mypinata", text.lower())
            self.assertNotIn("corvidlabs", text.lower())


class Page(unittest.TestCase):
    def test_page_shows_file_and_diff_on_loopback(self) -> None:
        # REQ-algit-4 REQ-algit-7
        with TemporaryDirectory() as tmp:
            repo = make_repo(Path(tmp), {"README.md": b"hello page\n"})
            httpd = serve(repo, port=0, mailbox="MAILBOXADDR", network="localnet", background=True)
            port = httpd.server_address[1]
            try:
                with urllib.request.urlopen(f"http://127.0.0.1:{port}/") as response:
                    html = response.read().decode()
                self.assertIn("<main", html)
                self.assertIn("Skip to the commit", html)
                self.assertIn('type="module"', html)
                self.assertIn("/brand/tokens.css", html)
                self.assertIn("Schibsted+Grotesk", html)
                self.assertIn("data-corvid-theme-toggle", html)
                self.assertNotIn("Avenir Next", html)
                with urllib.request.urlopen(f"http://127.0.0.1:{port}/brand/tokens.css") as tokens:
                    sheet = tokens.read().decode()
                self.assertIn("--paper", sheet)
                self.assertIn("#0E6F66", sheet)
                with urllib.request.urlopen(f"http://127.0.0.1:{port}/api/file?path=README.md") as response:
                    self.assertEqual(response.read(), b"hello page\n")
                with urllib.request.urlopen(f"http://127.0.0.1:{port}/api/diff?rev=HEAD") as response:
                    diff = response.read().decode()
                self.assertIn("hello page", diff)
                with self.assertRaises(urllib.error.HTTPError):
                    urllib.request.urlopen(f"http://127.0.0.1:{port}/api/file?path=../secret")
            finally:
                httpd.shutdown()


class LocalNet(unittest.TestCase):
    def test_push_and_clone_this_shape_of_repository(self) -> None:
        # REQ-algit-1 REQ-algit-3
        if not localnet_up():
            self.skipTest("LocalNet algod is not answering on 127.0.0.1:4001")
        with TemporaryDirectory() as tmp:
            repo = make_repo(Path(tmp), {"README.md": b"on chain\n"})
            head = git(repo, "rev-parse", "HEAD")
            state = push_localnet(repo, state_dir=str(Path(tmp) / "state"), env={})
            self.assertGreater(state["microalgo"], 0)
            built = clone_mailbox(state["mailbox"], str(Path(tmp) / "clone"))
            self.assertEqual(built["fsck_code"], 0)
            self.assertEqual(built["refs"]["refs/heads/main"], head)


class Command(unittest.TestCase):
    def test_help(self) -> None:
        # REQ-algit-7
        self.assertEqual(main(["--help"]), 0)


if __name__ == "__main__":
    unittest.main()
