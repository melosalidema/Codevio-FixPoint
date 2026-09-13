import { useQuery } from "@tanstack/react-query";
import { useMemo, useState } from "react";
import { Link } from "react-router-dom";

import { ProductCard } from "../components/ProductCard";
import { cn } from "../lib/cn";
import { platzi } from "../lib/platzi";

function SkeletonCard() {
  return (
    <div className="animate-pulse overflow-hidden rounded-2xl border border-stone-200 bg-white">
      <div className="aspect-square bg-stone-100" />
      <div className="space-y-2 p-4">
        <div className="h-3 w-16 rounded-full bg-stone-100" />
        <div className="h-4 w-3/4 rounded-full bg-stone-100" />
        <div className="h-3 w-full rounded-full bg-stone-100" />
        <div className="h-8 w-24 rounded-full bg-stone-100" />
      </div>
    </div>
  );
}

export function CatalogPage() {
  const [search, setSearch] = useState("");
  const [category, setCategory] = useState<string | null>(null);

  const productsQuery = useQuery({
    queryKey: ["platzi", "products"],
    queryFn: () => platzi.products(0, 50),
    staleTime: 5 * 60_000,
  });

  const products = productsQuery.data ?? [];

  const categories = useMemo(() => {
    const seen = new Map<string, string>();
    for (const product of products) {
      const slug = product.category?.slug;
      const name = product.category?.name;
      if (slug && name && !seen.has(slug)) seen.set(slug, name);
    }
    return [...seen.entries()].map(([slug, name]) => ({ slug, name })).sort((a, b) => a.name.localeCompare(b.name));
  }, [products]);

  const visible = useMemo(() => {
    const needle = search.trim().toLowerCase();
    return products.filter((product) => {
      if (category && product.category?.slug !== category) return false;
      if (!needle) return true;
      return (
        product.title.toLowerCase().includes(needle) ||
        product.description.toLowerCase().includes(needle) ||
        (product.category?.name ?? "").toLowerCase().includes(needle)
      );
    });
  }, [products, search, category]);

  return (
    <div className="space-y-8">
      <section className="overflow-hidden rounded-3xl border border-stone-200 bg-gradient-to-br from-orange-50 via-white to-emerald-50 px-6 py-10 sm:px-10 sm:py-14">
        <div className="max-w-2xl">
          <span className="inline-flex items-center gap-2 rounded-full border border-orange-200 bg-white px-3 py-1 text-xs font-medium text-orange-700">
            <span className="h-1.5 w-1.5 rounded-full bg-orange-500" />
            Powered by the Platzi Fake Store API + Fixpoint
          </span>
          <h1 className="mt-4 font-display text-3xl font-semibold leading-tight tracking-tight text-stone-900 sm:text-5xl">
            Buy something fake.
            <br />
            Get a refund that&apos;s <span className="text-orange-600">actually proven.</span>
          </h1>
          <p className="mt-4 max-w-xl text-sm leading-relaxed text-stone-600">
            Place a demo order, then file a refund from the order page. The Fixpoint agent investigates it across
            systems, clamps the amount to policy, and either settles it or pauses for a human — then proves what
            happened.
          </p>
          <div className="mt-7 flex flex-wrap gap-3">
            <a href="#catalog" className="btn-primary">
              Start shopping
            </a>
            <Link to="/orders" className="btn-ghost">
              Track my orders
            </Link>
          </div>
          <dl className="mt-8 flex flex-wrap gap-x-8 gap-y-3 text-xs text-stone-500">
            <div>
              <dt className="font-semibold text-stone-900">{products.length || "50"} products</dt>
              <dd>live from the Platzi API</dd>
            </div>
            <div>
              <dt className="font-semibold text-stone-900">30-day returns</dt>
              <dd>policy read by the agent</dd>
            </div>
            <div>
              <dt className="font-semibold text-stone-900">Verified refunds</dt>
              <dd>re-read from provider state</dd>
            </div>
          </dl>
        </div>
      </section>

      <div id="catalog" className="scroll-mt-28 space-y-4">
        <div className="flex flex-wrap items-center gap-3">
          <div className="relative w-full max-w-sm">
            <svg
              viewBox="0 0 24 24"
              className="pointer-events-none absolute left-3.5 top-1/2 h-4 w-4 -translate-y-1/2 text-stone-400"
              fill="none"
              stroke="currentColor"
              strokeWidth="2"
            >
              <circle cx="11" cy="11" r="7" />
              <path d="m20 20-3.5-3.5" strokeLinecap="round" />
            </svg>
            <input
              className="input pl-10"
              placeholder="Search products…"
              value={search}
              onChange={(event) => setSearch(event.target.value)}
              aria-label="Search products"
            />
          </div>
          <span className="ml-auto text-xs text-stone-400">
            {productsQuery.isSuccess ? `${visible.length} of ${products.length} products` : null}
          </span>
        </div>

        <div className="flex flex-wrap gap-1.5">
          <button
            type="button"
            className={cn(
              "chip",
              !category && "border-stone-900 bg-stone-900 text-white hover:border-stone-900 hover:text-white",
            )}
            onClick={() => setCategory(null)}
          >
            All
          </button>
          {categories.map((entry) => (
            <button
              key={entry.slug}
              type="button"
              className={cn(
                "chip",
                category === entry.slug &&
                  "border-stone-900 bg-stone-900 text-white hover:border-stone-900 hover:text-white",
              )}
              onClick={() => setCategory(category === entry.slug ? null : entry.slug)}
            >
              {entry.name}
            </button>
          ))}
        </div>
      </div>

      {productsQuery.isPending && (
        <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4">
          {Array.from({ length: 8 }).map((_, index) => (
            <SkeletonCard key={index} />
          ))}
        </div>
      )}

      {productsQuery.isError && (
        <div className="panel p-8 text-center">
          <p className="text-sm text-rose-600">
            Could not reach the Platzi Fake Store API. Check your network connection and try again.
          </p>
          <button type="button" className="btn-primary mt-4" onClick={() => productsQuery.refetch()}>
            Retry
          </button>
        </div>
      )}

      {productsQuery.isSuccess && visible.length === 0 && (
        <div className="panel p-10 text-center">
          <p className="text-sm text-stone-500">No products match this search. Try a different term or category.</p>
        </div>
      )}

      <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4">
        {visible.map((product) => (
          <ProductCard key={product.id} product={product} />
        ))}
      </div>
    </div>
  );
}
