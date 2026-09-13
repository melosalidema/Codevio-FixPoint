const usdFormatter = new Intl.NumberFormat("en-US", {
  style: "currency",
  currency: "USD",
});

/** Format integer cents as USD (e.g. 7900 -> "$79.00"). */
export function usd(cents: number): string {
  return usdFormatter.format(cents / 100);
}

/**
 * Platzi returns prices as JS numbers (whole dollars in observed data, but
 * decimals are possible). All internal money is integer cents.
 */
export function priceToCents(price: number): number {
  return Math.round(price * 100);
}

export function formatDate(iso: string): string {
  const date = new Date(iso);
  if (Number.isNaN(date.getTime())) return iso;
  return date.toLocaleString(undefined, {
    year: "numeric",
    month: "short",
    day: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  });
}
