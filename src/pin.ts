import { basename } from "node:path";
import { PinataSDK } from "pinata";

export interface Pinned {
  path: string;
  name: string;
  cid: string;
  bytes: number;
  url: string;
}

export function gatewayHost(raw: string): string {
  const trimmed = raw.trim().replace(/\/+$/, "");
  return trimmed.replace(/^https?:\/\//, "");
}

export function gatewayUrl(host: string, cid: string): string {
  return `https://${gatewayHost(host)}/ipfs/${cid}`;
}

export function clientFromEnv(env: NodeJS.ProcessEnv): PinataSDK {
  const jwt = env.PINATA_JWT?.trim();
  const gateway = env.PINATA_GATEWAY?.trim();
  if (!jwt || !gateway) {
    throw new Error("Set PINATA_JWT and PINATA_GATEWAY. See .env.example.");
  }
  return new PinataSDK({
    pinataJwt: jwt,
    pinataGateway: gatewayHost(gateway),
  });
}

export async function pinOne(
  pinata: PinataSDK,
  filePath: string,
  gateway: string,
): Promise<Pinned> {
  const name = basename(filePath);
  const bytes = new Uint8Array(await Bun.file(filePath).arrayBuffer());
  const uploaded = await pinata.upload.public.file(new File([bytes], name)).name(name);
  return {
    path: filePath,
    name,
    cid: uploaded.cid,
    bytes: uploaded.size,
    url: gatewayUrl(gateway, uploaded.cid),
  };
}
