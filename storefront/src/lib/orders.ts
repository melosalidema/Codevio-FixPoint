import type { PlatziProduct } from "./platzi";

export type CartLine = {
  product: PlatziProduct;
  quantity: number;
};

export type OrderItem = {
  id: string;
  productId: number;
  slug: string;
  title: string;
  priceCents: number;
  quantity: number;
  image: string | null;
  category: string;
  refundedAt?: string;
};

export type OrderRefund = {
  runId: string;
  itemIds: string[];
  submittedAt: string;
};

export type Order = {
  id: string;
  createdAt: string;
  customerName: string;
  customerEmail: string;
  items: OrderItem[];
  totalCents: number;
  refunds: OrderRefund[];
};

export type CustomerInfo = {
  name: string;
  email: string;
};

/**
 * The Fixpoint demo twins seed exactly one resolvable customer
 * (`jane@acme.com`). Using that identity lets the deterministic planner resolve
 * the customer instantly; the form is editable for other experiments.
 */
export const DEMO_CUSTOMER: CustomerInfo = { name: "Jane Doe", email: "jane@acme.com" };

const ORDER_ALPHABET = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789";

export function generateOrderId(): string {
  let suffix = "";
  for (let i = 0; i < 5; i += 1) {
    suffix += ORDER_ALPHABET[Math.floor(Math.random() * ORDER_ALPHABET.length)];
  }
  return `ORD-${suffix}`;
}

export function itemsTotalCents(items: Pick<OrderItem, "priceCents" | "quantity">[]): number {
  return items.reduce((sum, item) => sum + item.priceCents * item.quantity, 0);
}

export function orderFromCart(customer: CustomerInfo, cart: CartLine[]): Order {
  const items: OrderItem[] = cart.map((line) => ({
    id: `oi_${line.product.id}_${Math.random().toString(36).slice(2, 8)}`,
    productId: line.product.id,
    slug: line.product.slug,
    title: line.product.title,
    priceCents: Math.round(line.product.price * 100),
    quantity: line.quantity,
    image: line.product.images?.[0] ?? null,
    category: line.product.category?.name ?? "Uncategorized",
  }));

  return {
    id: generateOrderId(),
    createdAt: new Date().toISOString(),
    customerName: customer.name.trim(),
    customerEmail: customer.email.trim().toLowerCase(),
    items,
    totalCents: itemsTotalCents(items),
    refunds: [],
  };
}

export function refundableItems(order: Order): OrderItem[] {
  return order.items.filter((item) => !item.refundedAt);
}

export function orderStatus(order: Order): { label: string; tone: "paid" | "pending" | "refunded" | "partial" } {
  const refunded = order.items.filter((item) => item.refundedAt).length;
  if (refunded === order.items.length) return { label: "Refunded", tone: "refunded" };
  if (refunded > 0) return { label: `Partially refunded (${refunded}/${order.items.length})`, tone: "partial" };
  if (order.refunds.length > 0) return { label: "Refund in progress", tone: "pending" };
  return { label: "Paid", tone: "paid" };
}
