import { Link, useLocation, useParams } from "react-router-dom";

import { RefundPanel } from "../components/RefundPanel";
import { Panel, ProductImage, StatusPill } from "../components/Ui";
import { formatDate, usd } from "../lib/format";
import type { FormspreeResult } from "../lib/formspree";
import { orderStatus } from "../lib/orders";
import { useShop } from "../state/ShopContext";

const TONE_BY_STATUS = {
  paid: "info",
  pending: "pending",
  partial: "pending",
  refunded: "success",
} as const;

export function OrderPage() {
  const { orderId } = useParams<{ orderId: string }>();
  const location = useLocation();
  const { getOrder } = useShop();
  const order = orderId ? getOrder(orderId) : undefined;
  const orderNotification = (location.state as { orderNotification?: FormspreeResult } | null)
    ?.orderNotification;

  if (!order) {
    return (
      <Panel title="Order not found">
        <p className="py-8 text-center text-sm text-stone-500">This order does not exist in this browser.</p>
        <div className="text-center">
          <Link to="/orders" className="btn-ghost">
            Back to orders
          </Link>
        </div>
      </Panel>
    );
  }

  const status = orderStatus(order);

  return (
    <div className="space-y-5">
      <Link to="/orders" className="inline-flex items-center gap-1 text-sm text-stone-500 transition hover:text-stone-900">
        ← All orders
      </Link>

      {orderNotification && (
        <div
          className={
            orderNotification.ok
              ? "rounded-xl border border-emerald-200 bg-emerald-50 p-3.5 text-xs text-emerald-800"
              : "rounded-xl border border-amber-200 bg-amber-50 p-3.5 text-xs text-amber-800"
          }
        >
          {orderNotification.ok
            ? "Order notification emailed to the support inbox."
            : `Order placed, but the support notification could not be sent (${orderNotification.error}).`}
        </div>
      )}

      <div className="flex flex-wrap items-center gap-4 rounded-2xl border border-stone-200 bg-white p-5 shadow-card">
        <div className="min-w-[14rem] flex-1">
          <p className="text-xs font-medium uppercase tracking-wider text-stone-400">Order</p>
          <h1 className="font-mono text-2xl font-semibold text-stone-900">{order.id}</h1>
          <p className="mt-1 text-xs text-stone-500">
            Placed {formatDate(order.createdAt)} · {order.customerName} · {order.customerEmail}
          </p>
        </div>
        <StatusPill tone={TONE_BY_STATUS[status.tone]}>{status.label}</StatusPill>
        <div className="text-right">
          <p className="text-xs font-medium uppercase tracking-wider text-stone-400">Order total</p>
          <p className="text-2xl font-semibold text-stone-900">{usd(order.totalCents)}</p>
        </div>
      </div>

      <Panel title={`Items (${order.items.length})`}>
        <ul className="divide-y divide-stone-100">
          {order.items.map((item) => (
            <li key={item.id} className="flex flex-wrap items-center gap-4 py-4 first:pt-0 last:pb-0">
              <span className="h-16 w-16 shrink-0 overflow-hidden rounded-xl bg-stone-100">
                <ProductImage src={item.image} title={item.title} />
              </span>
              <div className="min-w-[10rem] flex-1">
                <p className="text-sm font-semibold text-stone-900">{item.title}</p>
                <p className="mt-0.5 text-xs text-stone-500">
                  {item.category} · {usd(item.priceCents)} × {item.quantity}
                </p>
              </div>
              {item.refundedAt && <StatusPill tone="success">refunded</StatusPill>}
              <span className="w-20 text-right text-sm font-semibold text-stone-900">
                {usd(item.priceCents * item.quantity)}
              </span>
            </li>
          ))}
        </ul>
      </Panel>

      <RefundPanel order={order} />
    </div>
  );
}
