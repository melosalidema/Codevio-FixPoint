/**
 * Thin client for the Platzi Fake Store API (https://fakeapi.platzi.com/).
 *
 * Only read-only product/category endpoints are used. The API allows any
 * origin (`access-control-allow-origin: *`), so the browser can call it
 * directly. The dataset is shared and publicly mutable: treat titles, prices
 * and images as display data only. Refunds are never computed from it — the
 * storefront's own order snapshot is the money record, mirroring Fixpoint's
 * "snapshot wins" safety principle.
 */

export type PlatziCategory = {
  id: number;
  name: string;
  slug: string;
  image?: string | null;
};

export type PlatziProduct = {
  id: number;
  title: string;
  slug: string;
  price: number;
  description: string;
  category?: PlatziCategory | null;
  images?: string[] | null;
};

const BASE_URL = import.meta.env.VITE_PLATZI_API_BASE ?? "https://api.escuelajs.co/api/v1";

export class PlatziError extends Error {
  status: number;

  constructor(status: number, message: string) {
    super(message);
    this.name = "PlatziError";
    this.status = status;
  }
}

async function get<T>(path: string): Promise<T> {
  let response: Response;
  try {
    response = await fetch(`${BASE_URL}${path}`, { headers: { Accept: "application/json" } });
  } catch {
    throw new PlatziError(0, "Platzi Fake Store API is unreachable");
  }
  if (!response.ok) {
    throw new PlatziError(response.status, `Platzi API error ${response.status}`);
  }
  return (await response.json()) as T;
}

/** Trim upstream noise: drop rows without a usable image/title/price. */
function sanitizeProduct(raw: PlatziProduct): PlatziProduct {
  const images = (raw.images ?? []).filter((url): url is string => typeof url === "string" && url.length > 0);
  return { ...raw, images };
}

export const platzi = {
  async products(offset = 0, limit = 50): Promise<PlatziProduct[]> {
    const rows = await get<PlatziProduct[]>(`/products?offset=${offset}&limit=${limit}`);
    return rows
      .filter((row) => row && typeof row.id === "number" && typeof row.title === "string")
      .map(sanitizeProduct);
  },

  async product(id: number | string): Promise<PlatziProduct> {
    return sanitizeProduct(await get<PlatziProduct>(`/products/${id}`));
  },

  categories(): Promise<PlatziCategory[]> {
    return get<PlatziCategory[]>("/categories");
  },
};

/** First usable image, if the product has one. */
export function productImage(product: Pick<PlatziProduct, "images" | "title">): string | null {
  return product.images?.[0] ?? null;
}

export function placeholderImage(title: string): string {
  return `https://placehold.co/600x400/1e293b/94a3b8?text=${encodeURIComponent(title.slice(0, 40))}`;
}
