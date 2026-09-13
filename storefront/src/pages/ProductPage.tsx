import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { Link, useParams } from "react-router-dom";

import { ProductImage, Spinner } from "../components/Ui";
import { usd } from "../lib/format";
import { platzi } from "../lib/platzi";
import { useShop } from "../state/ShopContext";

export function ProductPage() {
  const { productId } = useParams<{ productId: string }>();
  const { addToCart } = useShop();
  const [quantity, setQuantity] = useState(1);
  const [added, setAdded] = useState(false);

  const productQuery = useQuery({
    queryKey: ["platzi", "product", productId],
    queryFn: () => platzi.product(productId as string),
    enabled: Boolean(productId),
    staleTime: 5 * 60_000,
  });

  const product = productQuery.data;

  if (productQuery.isPending) {
    return (
      <div className="flex items-center justify-center gap-3 py-24 text-sm text-stone-500">
        <Spinner /> Loading product…
      </div>
    );
  }

  if (productQuery.isError || !product) {
    return (
      <div className="panel p-10 text-center">
        <p className="py-4 text-sm text-stone-500">
          This product is not available (it may have been deleted upstream).
        </p>
        <Link to="/" className="btn-primary">
          Back to shop
        </Link>
      </div>
    );
  }

  const unitCents = Math.round(product.price * 100);

  return (
    <div className="space-y-5">
      <nav className="text-sm text-stone-500">
        <Link to="/" className="transition hover:text-stone-900">
          Shop
        </Link>
        <span className="mx-2 text-stone-300">/</span>
        <span className="text-stone-900">{product.title}</span>
      </nav>

      <div className="grid gap-8 lg:grid-cols-2">
        <div className="space-y-3">
          <div className="overflow-hidden rounded-2xl border border-stone-200 bg-stone-100">
            <div className="aspect-square">
              <ProductImage src={product.images?.[0] ?? null} title={product.title} />
            </div>
          </div>
          {product.images && product.images.length > 1 && (
            <div className="grid grid-cols-4 gap-3">
              {product.images.slice(1, 5).map((image, index) => (
                <div
                  key={`${image}-${index}`}
                  className="aspect-square overflow-hidden rounded-xl border border-stone-200 bg-stone-100"
                >
                  <ProductImage src={image} title={product.title} />
                </div>
              ))}
            </div>
          )}
        </div>

        <div className="space-y-5">
          <div>
            <span className="inline-flex rounded-full bg-orange-50 px-3 py-1 text-xs font-medium text-orange-700">
              {product.category?.name ?? "Uncategorized"}
            </span>
            <h1 className="mt-3 font-display text-2xl font-semibold leading-tight tracking-tight text-stone-900 sm:text-3xl">
              {product.title}
            </h1>
            <p className="mt-3 text-3xl font-semibold text-stone-900">{usd(unitCents)}</p>
          </div>

          <p className="text-sm leading-relaxed text-stone-600">{product.description}</p>

          <div className="rounded-2xl border border-stone-200 bg-white p-5 shadow-card">
            <div className="flex flex-wrap items-center gap-4">
              <span className="text-sm font-medium text-stone-700">Quantity</span>
              <div className="inline-flex items-center rounded-full border border-stone-300 bg-white">
                <button
                  type="button"
                  className="flex h-9 w-9 items-center justify-center rounded-l-full text-stone-500 transition hover:bg-stone-100 hover:text-stone-900"
                  onClick={() => setQuantity((value) => Math.max(1, value - 1))}
                  aria-label="Decrease quantity"
                >
                  −
                </button>
                <span id="quantity" className="min-w-[2.5rem] text-center text-sm font-semibold text-stone-900">
                  {quantity}
                </span>
                <button
                  type="button"
                  className="flex h-9 w-9 items-center justify-center rounded-r-full text-stone-500 transition hover:bg-stone-100 hover:text-stone-900"
                  onClick={() => setQuantity((value) => Math.min(10, value + 1))}
                  aria-label="Increase quantity"
                >
                  +
                </button>
              </div>
              <span className="ml-auto text-sm text-stone-500">
                Subtotal <span className="font-semibold text-stone-900">{usd(unitCents * quantity)}</span>
              </span>
            </div>

            <div className="mt-5 flex flex-wrap gap-2">
              <button
                type="button"
                className="btn-primary"
                onClick={() => {
                  addToCart(product, quantity);
                  setAdded(true);
                }}
              >
                Add to cart
              </button>
              <Link
                to="/cart"
                className="btn-ghost"
                onClick={() => {
                  if (!added) addToCart(product, quantity);
                }}
              >
                Go to cart
              </Link>
            </div>

            {added && (
              <p className="mt-3 text-xs text-emerald-700">
                Added {quantity} × {product.title} to your cart.
              </p>
            )}
          </div>

          <p className="rounded-xl border border-stone-200 bg-stone-50 p-3 text-xs leading-relaxed text-stone-500">
            Demo only: no payment is taken. Product data comes from the Platzi Fake Store API and can change at any
            time; your order keeps the price snapshot shown here.
          </p>
        </div>
      </div>
    </div>
  );
}
