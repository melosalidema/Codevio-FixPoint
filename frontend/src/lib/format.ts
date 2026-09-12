/** USD formatting from integer cents. */
export function usd(cents: number | null | undefined): string {
  if (cents === null || cents === undefined) return "-";
  return (cents / 100).toLocaleString("en-US", { style: "currency", currency: "USD" });
}

/** Short display form of an integer amount in cents. */
export function cents(centsValue: number | null | undefined): string {
  return centsValue === null || centsValue === undefined ? "-" : String(centsValue);
}

/** Human readable timestamp. */
export function when(value: string | null | undefined): string {
  if (!value) return "-";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value;
  return date.toLocaleString();
}

/** Shorten a hash for display while keeping it recognizable. */
export function shortHash(hash: string | null | undefined, length = 20): string {
  if (!hash) return "-";
  return hash.length > length ? `${hash.slice(0, length)}…` : hash;
}

export function titleCase(value: string): string {
  return value.replace(/_/g, " ");
}

/** Compact JSON with a stable key order and a length cap. */
export function prettyJson(value: unknown, maxLength = 220): string {
  if (value === null || value === undefined) return "";
  const text = JSON.stringify(value);
  return text.length > maxLength ? `${text.slice(0, maxLength)}…` : text;
}
