import { useState, type FormEvent } from "react";
import { Link, useNavigate } from "react-router-dom";

import { Panel, Spinner } from "../components/Ui";
import { usd } from "../lib/format";
import { notifyOrderPlaced } from "../lib/formspree";
import { DEMO_CUSTOMER } from "../lib/orders";
import { useShop } from "../state/ShopContext";

export function CheckoutPage() {
  const { cart, cartTotalCents, customer, setCustomer, placeOrder } = useShop();
  const navigate = useNavigate();
  const [name, setName] = useState(customer.name || DEMO_CUSTOMER.name);
  const [email, setEmail] = useState(customer.email || DEMO_CUSTOMER.email);
  const [error, setError] = useState("");
  const [submitting, setSubmitting] = useState(false);

  if (cart.length === 0) {
    return (
      <Panel title="Checkout">
        <p className="py-8 text-center text-sm text-stone-500">
          Your cart is empty, so there is nothing to check out.
        </p>
        <div className="text-center">
          <Link to="/" className="btn-primary">
            Browse products
          </Link>
        </div>
      </Panel>
    );
  }

  async function handleSubmit(event: FormEvent) {
    event.preventDefault();
    const trimmedName = name.trim();
    const trimmedEmail = email.trim().toLowerCase();
    if (!trimmedName) {
      setError("Please enter the customer name.");
      return;
    }
    if (!/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(trimmedEmail)) {
      setError("Please enter a valid email address.");
      return;
    }
    setError("");
    const info = { name: trimmedName, email: trimmedEmail };
    setCustomer(info);
    const order = placeOrder(info);
    if (!order) return;
    // Notify the support mailbox via Formspree, then hand the result to the
    // order page so the customer (and the demo operator) can see it.
    setSubmitting(true);
    const orderNotification = await notifyOrderPlaced(order);
    navigate(`/orders/${order.id}`, { state: { orderNotification } });
  }

  return (
    <div className="grid gap-6 lg:grid-cols-[1fr_22rem]">
      <Panel title="Customer">
        <form onSubmit={handleSubmit} className="space-y-5">
          <div>
            <label
              htmlFor="customer-name"
              className="mb-1.5 block text-xs font-medium uppercase tracking-wider text-stone-500"
            >
              Full name
            </label>
            <input
              id="customer-name"
              className="input"
              value={name}
              onChange={(event) => setName(event.target.value)}
              placeholder="Jane Doe"
              autoComplete="name"
            />
          </div>
          <div>
            <label
              htmlFor="customer-email"
              className="mb-1.5 block text-xs font-medium uppercase tracking-wider text-stone-500"
            >
              Email
            </label>
            <input
              id="customer-email"
              type="email"
              className="input"
              value={email}
              onChange={(event) => setEmail(event.target.value)}
              placeholder="jane@acme.com"
              autoComplete="email"
            />
            <p className="mt-2 text-xs text-stone-500">
              Demo tip: <span className="code">jane@acme.com</span> is the seeded customer the Fixpoint twins can
              resolve. Other emails may be escalated as unknown.
            </p>
          </div>

          {error && <p className="text-sm text-rose-600">{error}</p>}

          <div className="rounded-xl border border-orange-200 bg-orange-50 p-3.5 text-xs leading-relaxed text-orange-800">
            No card is charged and no real payment happens. Placing the order creates a local order with an immutable
            price snapshot, exactly the record the refund agent will work from.
          </div>

          <div className="flex flex-wrap gap-2">
            <button type="submit" className="btn-primary" disabled={submitting}>
              {submitting && <Spinner className="h-4 w-4" />}
              {submitting ? "Placing order…" : `Place demo order · ${usd(cartTotalCents)}`}
            </button>
            <Link to="/cart" className="btn-ghost">
              Back to cart
            </Link>
          </div>
        </form>
      </Panel>

      <Panel title="Order summary">
        <ul className="space-y-3">
          {cart.map((line) => (
            <li key={line.product.id} className="flex items-start justify-between gap-3 text-sm">
              <span className="text-stone-700">
                {line.product.title}
                <span className="text-stone-400"> × {line.quantity}</span>
              </span>
              <span className="whitespace-nowrap font-semibold text-stone-900">
                {usd(Math.round(line.product.price * 100) * line.quantity)}
              </span>
            </li>
          ))}
        </ul>
        <div className="mt-4 flex items-center justify-between border-t border-stone-200 pt-3">
          <span className="text-sm text-stone-500">Total</span>
          <span className="text-xl font-semibold text-stone-900">{usd(cartTotalCents)}</span>
        </div>
      </Panel>
    </div>
  );
}
