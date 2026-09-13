import { Link } from "react-router-dom";

import { Panel, ProductImage, StatusPill } from "../components/Ui";
import { formatDate, usd } from "../lib/format";
import { orderStatus } from "../lib/orders";
import { useShop } from "../state/ShopContext";

const TONE_BY_STATUS = {
  paid: "info",
  pending: "pending",
  partial: "pending",
  refunded: "success",
} as const;

export function OrdersPage() {
  const { orders } = useShop();

  if (orders.length === 0) {
    return (
      <Panel title="Your orders">
        <p className="py-8 text-center text-sm text-stone-500">You have not placed any demo orders yet.</p>
        <div className="text-center">
          <Link to="/" className="btn-primary">
            Browse products
          </Link>
        </div>
      </Panel>
    );
  }

  return (
    <div className="space-y-4">
      <Panel title={`Your orders (${orders.length})`}>
        <ul className="divide-y divide-stone-100">
          {orders.map((order) => {
            const status = orderStatus(order);
            return (
              <li key={order.id} className="flex flex-wrap items-center gap-4 py-5 first:pt-0 last:pb-0">
                <div className="flex -space-x-3">
                  {order.items.slice(0, 4).map((item) => (
                    <span
                      key={item.id}
                      className="h-14 w-14 overflow-hidden rounded-xl border-2 border-white bg-stone-100 shadow-card"
                    >
                      <ProductImage src={item.image} title={item.title} />
                    </span>
                  ))}
                </div>
                <div className="min-w-[12rem] flex-1">
                  <Link
                    to={`/orders/${order.id}`}
                    className="font-mono text-sm font-semibold text-stone-900 transition hover:text-orange-600"
                  >
                    {order.id}
                  </Link>
                  <p className="mt-0.5 text-xs text-stone-500">
                    {formatDate(order.createdAt)} · {order.items.length}{" "}
                    {order.items.length === 1 ? "item" : "items"}
                  </p>
                </div>
                <StatusPill tone={TONE_BY_STATUS[status.tone]}>{status.label}</StatusPill>
                <span className="w-20 text-right text-sm font-semibold text-stone-900">{usd(order.totalCents)}</span>
                <Link to={`/orders/${order.id}`} className="btn-ghost px-4 py-1.5 text-xs">
                  View
                </Link>
              </li>
            );
          })}
        </ul>
      </Panel>
      <p className="px-1 text-xs text-stone-500">
        Orders live in this browser (localStorage). Each one carries the price snapshot used by the refund agent.
      </p>
    </div>
  );
}
