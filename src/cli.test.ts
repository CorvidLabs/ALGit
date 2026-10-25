import { mkdtemp, mkdir, symlink, writeFile } from "node:fs/promises";
import { tmpdir } from "node:os";
import path from "node:path";
import { describe, expect, test } from "bun:test";
import { collect } from "./files.ts";
import { main } from "./cli.ts";
import { gatewayHost, gatewayUrl } from "./pin.ts";
import { overFreePlan } from "./plan.ts";

describe("free plan", () => {
  test("allows a small batch", () => {
    expect(overFreePlan({ files: 2, bytes: 100 }, false)).toBeNull();
  });

  test("stops above 500 files", () => {
    expect(overFreePlan({ files: 501, bytes: 10 }, false)).toContain("500");
  });

  test("stops above 1 GB", () => {
    expect(overFreePlan({ files: 1, bytes: 1_000_000_001 }, false)).toContain("1000000000");
  });

  test("a paid plan lifts the stop", () => {
    expect(overFreePlan({ files: 9000, bytes: 2_000_000_000 }, true)).toBeNull();
  });
});

describe("files", () => {
  test("lists files and skips .git", async () => {
    const root = await mkdtemp(path.join(tmpdir(), "algit-"));
    await writeFile(path.join(root, "a.txt"), "a");
    await mkdir(path.join(root, ".git"));
    await writeFile(path.join(root, ".git", "secret"), "no");
    await mkdir(path.join(root, "nested"));
    await writeFile(path.join(root, "nested", "b.txt"), "bb");
    await symlink(path.join(root, "a.txt"), path.join(root, "link.txt"));

    const files = await collect([root]);
    expect(files.map((file) => path.basename(file.path))).toEqual(["a.txt", "b.txt"]);
    expect(files.reduce((sum, file) => sum + file.bytes, 0)).toBe(3);
  });
});

describe("gateway", () => {
  test("builds a CID url", () => {
    expect(gatewayHost("https://corvid.mypinata.cloud/")).toBe("corvid.mypinata.cloud");
    expect(gatewayUrl("corvid.mypinata.cloud", "bafytest")).toBe(
      "https://corvid.mypinata.cloud/ipfs/bafytest",
    );
  });
});

describe("cli", () => {
  test("help does not need a key", async () => {
    expect(await main(["--help"], {})).toBe(0);
  });

  test("pin without a key fails before any upload", async () => {
    const root = await mkdtemp(path.join(tmpdir(), "algit-"));
    await writeFile(path.join(root, "a.txt"), "a");
    expect(await main(["pin", root], {})).toBe(1);
  });
});
