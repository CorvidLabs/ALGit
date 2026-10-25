/** Pinata Free, as listed on pinata.cloud/pricing. Storage is decimal GB. */
export const FREE_PLAN = {
  maxFiles: 500,
  maxBytes: 1_000_000_000,
  bandwidthBytes: 10_000_000_000,
  requests: 10_000,
  gateways: 1,
} as const;

export interface Batch {
  files: number;
  bytes: number;
}

export function overFreePlan(batch: Batch, paid: boolean): string | null {
  if (paid) return null;
  if (batch.files > FREE_PLAN.maxFiles) {
    return `${batch.files} files is over the free plan limit of ${FREE_PLAN.maxFiles}. Pass --paid for the Picnic plan.`;
  }
  if (batch.bytes > FREE_PLAN.maxBytes) {
    return `${batch.bytes} bytes is over the free plan limit of ${FREE_PLAN.maxBytes}. Pass --paid for the Picnic plan.`;
  }
  return null;
}
