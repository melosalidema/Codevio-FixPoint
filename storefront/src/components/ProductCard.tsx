import { Link } from "react-router-dom";

import { usd } from "../lib/format";
import type { PlatziProduct } from "../lib/platzi";
import { useShop } from "../state/ShopContext";
import { ProductImage } from "./Ui";

export function ProductCard({ product }: { product: PlatziProduct }) {
  const { addToCart } = useShop();

  return (
    <article className="group flex flex-col overflow-hidden rounded-2xl border border-stone-200 bg-white transition duration-200 hover:-translate-y-0.5 hover:shadow-lift">
      <Link to={`/product/${product.id}`} className="block aspect-square overflow-hidden bg-stone-100">
        <ProductImage
          src={product.images?.[0] ?? null}
          title={product.title}
          className="transition duration-500 group-hover:scale-105"
        />
      </Link>
      <div className="flex flex-1 flex-col gap-1.5 p-4">
        <span className="text-[11px] font-medium uppercase tracking-wider text-orange-600">
          {product.category?.name ?? "Uncategorized"}
        </span>
        <Link
          to={`/product/${product.id}`}
          className="line-clamp-2 text-sm font-semibold text-stone-900 hover:underline"
        >
          {product.title}
        </Link>
        <p className="line-clamp-2 flex-1 text-xs leading-relaxed text-stone-500">{product.description}</p>
        <div className="mt-2 flex items-center justify-between gap-2">
          <span className="text-base font-semibold text-stone-900">{usd(Math.round(product.price * 100))}</span>
          <button
            type="button"
            className="inline-flex h-9 items-center gap-1.5 rounded-full bg-stone-900 px-3.5 text-xs font-medium text-white transition hover:bg-orange-600"
            onClick={() => addToCart(product, 1)}
            aria-label={`Add ${product.title} to cart`}
          >
            <svg viewBox="0 0 24 24" className="h-3.5 w-3.5" fill="none" stroke="currentColor" strokeWidth="2">
              <path d="M12 5v14M5 12h14" strokeLinecap="round" />
            </svg>
            Add
          </button>
        </div>
      </div>
    </article>
  );
}
