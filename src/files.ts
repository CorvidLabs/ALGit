import { lstat, readdir } from "node:fs/promises";
import path from "node:path";

const SKIP = new Set([".git", "node_modules"]);

export interface LocalFile {
  path: string;
  bytes: number;
}

export async function collect(inputs: string[]): Promise<LocalFile[]> {
  const found: LocalFile[] = [];
  for (const input of inputs) {
    await walk(path.resolve(input), found);
  }
  found.sort((a, b) => a.path.localeCompare(b.path));
  return found;
}

async function walk(target: string, found: LocalFile[]): Promise<void> {
  const info = await lstat(target);
  if (info.isSymbolicLink()) return;
  if (info.isFile()) {
    found.push({ path: target, bytes: info.size });
    return;
  }
  if (!info.isDirectory()) return;
  const entries = await readdir(target, { withFileTypes: true });
  for (const entry of entries) {
    if (SKIP.has(entry.name)) continue;
    await walk(path.join(target, entry.name), found);
  }
}
