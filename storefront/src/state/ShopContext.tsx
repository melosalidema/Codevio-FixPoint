import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useState,
  type ReactNode,
} from "react";

import {
  DEMO_CUSTOMER,
  itemsTotalCents,
  orderFromCart,
  type CartLine,
  type CustomerInfo,
  type Order,
  type OrderRefund,
} from "../lib/orders";
import type { PlatziProduct } from "../lib/platzi";

const CART_KEY = "fixpoint-store.cart.v1";
const ORDERS_KEY = "fixpoint-store.orders.v1";
const CUSTOMER_KEY = "fixpoint-store.customer.v1";

function readJson<T>(key: string, fallback: T): T {
  try {
    const raw = window.localStorage.getItem(key);
    if (!raw) return fallback;
    return JSON.parse(raw) as T;
  } catch {
    return fallback;
  }
}

type ShopContextValue = {
  cart: CartLine[];
  orders: Order[];
  customer: CustomerInfo;
  cartCount: number;
  cartTotalCents: number;
  addToCart: (product: PlatziProduct, quantity?: number) => void;
  setQuantity: (productId: number, quantity: number) => void;
  removeFromCart: (productId: number) => void;
  clearCart: () => void;
  setCustomer: (customer: CustomerInfo) => void;
  placeOrder: (customer?: CustomerInfo) => Order | null;
  getOrder: (orderId: string) => Order | undefined;
  addRefund: (orderId: string, refund: OrderRefund) => void;
  markRefunded: (orderId: string, itemIds: string[]) => void;
};

const ShopContext = createContext<ShopContextValue | null>(null);

export function ShopProvider({ children }: { children: ReactNode }) {
  const [cart, setCart] = useState<CartLine[]>(() => readJson(CART_KEY, [] as CartLine[]));
  const [orders, setOrders] = useState<Order[]>(() => readJson(ORDERS_KEY, [] as Order[]));
  const [customer, setCustomer] = useState<CustomerInfo>(() => readJson(CUSTOMER_KEY, DEMO_CUSTOMER));

  useEffect(() => {
    window.localStorage.setItem(CART_KEY, JSON.stringify(cart));
  }, [cart]);

  useEffect(() => {
    window.localStorage.setItem(ORDERS_KEY, JSON.stringify(orders));
  }, [orders]);

  useEffect(() => {
    window.localStorage.setItem(CUSTOMER_KEY, JSON.stringify(customer));
  }, [customer]);

  const addToCart = useCallback((product: PlatziProduct, quantity = 1) => {
    setCart((current) => {
      const existing = current.find((line) => line.product.id === product.id);
      if (existing) {
        return current.map((line) =>
          line.product.id === product.id ? { ...line, quantity: line.quantity + quantity } : line,
        );
      }
      return [...current, { product, quantity }];
    });
  }, []);

  const setQuantity = useCallback((productId: number, quantity: number) => {
    setCart((current) => {
      if (quantity < 1) return current.filter((line) => line.product.id !== productId);
      return current.map((line) => (line.product.id === productId ? { ...line, quantity } : line));
    });
  }, []);

  const removeFromCart = useCallback((productId: number) => {
    setCart((current) => current.filter((line) => line.product.id !== productId));
  }, []);

  const clearCart = useCallback(() => setCart([]), []);

  const placeOrder = useCallback(
    (override?: CustomerInfo): Order | null => {
      if (cart.length === 0) return null;
      const order = orderFromCart(override ?? customer, cart);
      setOrders((current) => [order, ...current]);
      setCart([]);
      return order;
    },
    [cart, customer],
  );

  const getOrder = useCallback(
    (orderId: string) => orders.find((order) => order.id === orderId),
    [orders],
  );

  const addRefund = useCallback((orderId: string, refund: OrderRefund) => {
    setOrders((current) =>
      current.map((order) =>
        order.id === orderId ? { ...order, refunds: [...order.refunds, refund] } : order,
      ),
    );
  }, []);

  const markRefunded = useCallback((orderId: string, itemIds: string[]) => {
    const ids = new Set(itemIds);
    setOrders((current) =>
      current.map((order) => {
        if (order.id !== orderId) return order;
        if (!order.items.some((item) => ids.has(item.id) && !item.refundedAt)) return order;
        return {
          ...order,
          items: order.items.map((item) =>
            ids.has(item.id) && !item.refundedAt ? { ...item, refundedAt: new Date().toISOString() } : item,
          ),
        };
      }),
    );
  }, []);

  const value = useMemo<ShopContextValue>(() => {
    return {
      cart,
      orders,
      customer,
      cartCount: cart.reduce((sum, line) => sum + line.quantity, 0),
      cartTotalCents: itemsTotalCents(
        cart.map((line) => ({ priceCents: Math.round(line.product.price * 100), quantity: line.quantity })),
      ),
      addToCart,
      setQuantity,
      removeFromCart,
      clearCart,
      setCustomer,
      placeOrder,
      getOrder,
      addRefund,
      markRefunded,
    };
  }, [
    cart,
    orders,
    customer,
    addToCart,
    setQuantity,
    removeFromCart,
    clearCart,
    placeOrder,
    getOrder,
    addRefund,
    markRefunded,
  ]);

  return <ShopContext.Provider value={value}>{children}</ShopContext.Provider>;
}

export function useShop(): ShopContextValue {
  const context = useContext(ShopContext);
  if (!context) throw new Error("useShop must be used inside ShopProvider");
  return context;
}
