/**
 * Formspree notifications (https://formspree.io/f/xaeygdwn).
 *
 * The storefront uses Formspree's AJAX submit endpoint — the same endpoint the
 * official React SDK wraps — because order and refund notifications are
 * programmatic events, not a single user-filled form. Submissions arrive in the
 * linked mailbox as email notifications.
 *
 * Special fields used:
 *   email    -> sets the notification's Reply-To to the customer
 *   subject  -> notification subject line
 *   _gotcha  -> honeypot; must stay empty for real submissions
 *
 * Never trust these fields downstream: they are customer input, exactly like
 * the request text the Fixpoint quarantine parser already treats as data.
 */

import { usd } from "./format";
import type { Order, OrderItem } from "./orders";
import type { RefundReason } from "./refund";

const DEFAULT_FORM_ID = "xaeygdwn";

/** Public form id; override with VITE_FORMSPREE_FORM_ID if the form changes. */
export const FORMSPREE_FORM_ID = import.meta.env.VITE_FORMSPREE_FORM_ID ?? DEFAULT_FORM_ID;

export type FormspreeResult = { ok: true } | { ok: false; error: string };

/** POST JSON to Formspree. Never throws; callers decide how to surface errors. */
export async function submitToFormspree(fields: Record<string, string>): Promise<FormspreeResult> {
  const controller = new AbortController();
  const timeout = window.setTimeout(() => controller.abort(), 6_000);
  try {
    const response = await fetch(`https://formspree.io/f/${FORMSPREE_FORM_ID}`, {
      method: "POST",
      headers: {
        Accept: "application/json",
        "Content-Type": "application/json",
      },
      body: JSON.stringify({ ...fields, _gotcha: "" }),
      signal: controller.signal,
    });

    if (!response.ok) {
      let detail = `HTTP ${response.status}`;
      try {
        const body = (await response.json()) as { errors?: { message?: string }[] };
        const first = body.errors?.[0]?.message;
        if (first) detail = first;
      } catch {
        // Non-JSON error body; keep the status text.
      }
      return { ok: false, error: detail };
    }
    return { ok: true };
  } catch {
    return { ok: false, error: "network unreachable" };
  } finally {
    window.clearTimeout(timeout);
  }
}

function itemsSummary(items: OrderItem[]): string {
  return items.map((item) => `${item.title} x${item.quantity}`).join("; ");
}

export function notifyOrderPlaced(order: Order): Promise<FormspreeResult> {
  return submitToFormspree({
    event: "order_placed",
    subject: `New order ${order.id} · ${usd(order.totalCents)}`,
    email: order.customerEmail,
    customer_name: order.customerName,
    order_id: order.id,
    amount_display: usd(order.totalCents),
    amount_cents: String(order.totalCents),
    item_count: String(order.items.length),
    items: itemsSummary(order.items),
    placed_at: order.createdAt,
  });
}

export function notifyRefundRequested(input: {
  order: Order;
  items: OrderItem[];
  reason: RefundReason;
  note: string;
  totalCents: number;
  requestText: string;
  runId?: string;
}): Promise<FormspreeResult> {
  const { order, items, reason, note, totalCents, requestText, runId } = input;
  return submitToFormspree({
    event: "refund_requested",
    subject: `Refund request ${order.id} · ${usd(totalCents)}`,
    email: order.customerEmail,
    customer_name: order.customerName,
    order_id: order.id,
    amount_display: usd(totalCents),
    amount_cents: String(totalCents),
    reason: reason.label,
    note,
    items: itemsSummary(items),
    request_text: requestText,
    run_id: runId ?? "",
  });
}
