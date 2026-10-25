import { collect } from "./files.ts";
import { overFreePlan } from "./plan.ts";
import { clientFromEnv, pinOne } from "./pin.ts";

const USAGE = `algit pin [--paid] <file-or-directory>...

Pins those files to the Pinata account in PINATA_JWT.
The free plan stops at 500 files or 1 GB in one batch. --paid lifts that stop.
There is no server and no upload page.
`;

export async function main(argv: string[], env: NodeJS.ProcessEnv): Promise<number> {
  const [command, ...rest] = argv;
  if (command !== "pin") {
    console.log(USAGE);
    return command === undefined || command === "--help" || command === "-h" ? 0 : 2;
  }
  const paid = rest.includes("--paid");
  const inputs = rest.filter((arg) => arg !== "--paid");
  if (inputs.length === 0) {
    console.error("Name at least one file or directory.");
    console.log(USAGE);
    return 2;
  }

  const files = await collect(inputs);
  if (files.length === 0) {
    console.error("No files found.");
    return 1;
  }
  const reason = overFreePlan(
    { files: files.length, bytes: files.reduce((sum, file) => sum + file.bytes, 0) },
    paid,
  );
  if (reason) {
    console.error(reason);
    return 1;
  }

  try {
    const gateway = env.PINATA_GATEWAY ?? "";
    const pinata = clientFromEnv(env);
    for (const file of files) {
      const pinned = await pinOne(pinata, file.path, gateway);
      console.log(`${pinned.cid}\t${pinned.bytes}\t${pinned.url}\t${pinned.path}`);
    }
  } catch (error) {
    console.error(error instanceof Error ? error.message : String(error));
    return 1;
  }
  return 0;
}

if (import.meta.main) {
  process.exit(await main(process.argv.slice(2), process.env));
}
