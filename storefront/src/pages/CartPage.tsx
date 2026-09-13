import { Link, useNavigate } from "react-router-dom";

import { Panel, ProductImage } from "../components/Ui";
import { usd } from "../lib/format";
import { useShop } from "../state/ShopContext";

export function CartPage() {
  const { cart, cartTotalCents, setQuantity, removeFromCart, clearCart } = useShop();
  const navigate = useNavigate();

  if (cart.length === 0) {
    return (
      <Panel title="Your cart">
        <p className="py-8 text-center text-sm text-stone-500">Your cart is empty.</p>
        <div className="text-center">
          <Link to="/" className="btn-primary">
            Browse products
          </Link>
        </div>
      </Panel>
    );
  }

  return (
    <div className="grid gap-6 lg:grid-cols-[1fr_22rem]">
      <Panel title={`Cart (${cart.length} ${cart.length === 1 ? "item" : "items"})`}>
        <ul className="divide-y divide-stone-100">
          {cart.map((line) => {
            const unitCents = Math.round(line.product.price * 100);
            return (
              <li key={line.product.id} className="flex flex-wrap items-center gap-4 py-5 first:pt-0 last:pb-0">
                <Link
                  to={`/product/${line.product.id}`}
                  className="h-20 w-20 shrink-0 overflow-hidden rounded-xl bg-stone-100"
                >
                  <ProductImage src={line.product.images?.[0] ?? null} title={line.product.title} />
                </Link>
                <div className="min-w-[10rem] flex-1">
                  <Link
                    to={`/product/${line.product.id}`}
                    className="text-sm font-semibold text-stone-900 hover:underline"
                  >
                    {line.product.title}
                  </Link>
                  <p className="mt-0.5 text-xs text-stone-500">
                    {usd(unitCents)} · {line.product.category?.name ?? "Uncategorized"}
                  </p>
                </div>
                <div className="inline-flex items-center rounded-full border border-stone-300 bg-white">
                  <button
                    type="button"
                    className="flex h-8 w-8 items-center justify-center rounded-l-full text-stone-500 transition hover:bg-stone-100 hover:text-stone-900"
                    onClick={() => setQuantity(line.product.id, line.quantity - 1)}
                    aria-label={`Decrease quantity of ${line.product.title}`}
                  >
                    −
                  </button>
                  <span className="min-w-[2rem] text-center text-sm font-medium text-stone-900">{line.quantity}</span>
                  <button
                    type="button"
                    className="flex h-8 w-8 items-center justify-center rounded-r-full text-stone-500 transition hover:bg-stone-100 hover:text-stone-900"
                    onClick={() => setQuantity(line.product.id, line.quantity + 1)}
                    aria-label={`Increase quantity of ${line.product.title}`}
                  >
                    +
                  </button>
                </div>
                <span className="w-20 text-right text-sm font-semibold text-stone-900">
                  {usd(unitCents * line.quantity)}
                </span>
                <button
                  type="button"
                  className="text-xs font-medium text-stone-400 transition hover:text-rose-600"
                  onClick={() => removeFromCart(line.product.id)}
                >
                  Remove
                </button>
              </li>
            );
          })}
        </ul>
      </Panel>

      <div className="space-y-4">
        <Panel title="Summary">
          <dl className="space-y-2.5 text-sm">
            <div className="flex items-center justify-between text-stone-600">
              <dt>Subtotal</dt>
              <dd className="font-medium text-stone-900">{usd(cartTotalCents)}</dd>
            </div>
            <div className="flex items-center justify-between text-stone-400">
              <dt>Shipping</dt>
              <dd>Free</dd>
            </div>
            <div className="flex items-center justify-between border-t border-stone-200 pt-3">
              <dt className="font-medium text-stone-900">Total</dt>
              <dd className="text-xl font-semibold text-stone-900">{usd(cartTotalCents)}</dd>
            </div>
          </dl>

          <button type="button" className="btn-primary mt-5 w-full" onClick={() => navigate("/checkout")}>
            Checkout
          </button>
          <button
            type="button"
            className="mt-3 w-full text-center text-xs font-medium text-stone-400 transition hover:text-stone-700"
            onClick={clearCart}
          >
            Clear cart
          </button>
        </Panel>

        <p className="px-1 text-xs leading-relaxed text-stone-500">
          Demo checkout: no payment is taken. You will get an order page with a “Request a refund” option that calls
          your Fixpoint agent.
        </p>
      </div>
    </div>
  );
}
