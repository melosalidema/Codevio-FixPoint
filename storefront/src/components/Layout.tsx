import { Link, NavLink, Outlet } from "react-router-dom";

import { cn } from "../lib/cn";
import { CONSOLE_URL } from "../lib/fixpoint";
import { useFixpointConfig } from "../lib/hooks";
import { useShop } from "../state/ShopContext";

function FixpointStatus() {
  const config = useFixpointConfig();

  const up = config.isSuccess;
  const offline = config.isError;

  return (
    <div
      className={cn(
        "flex items-center gap-2 rounded-full border px-3 py-1 text-xs font-medium",
        up && "border-emerald-200 bg-emerald-50 text-emerald-700",
        offline && "border-rose-200 bg-rose-50 text-rose-700",
        !up && !offline && "border-stone-200 bg-stone-50 text-stone-500",
      )}
      title={
        up
          ? `Fixpoint ${config.data.version} · planner ${config.data.llm_enabled ? "llm" : "deterministic"}`
          : "Fixpoint control plane on http://127.0.0.1:8000"
      }
    >
      <span
        className={cn(
          "h-2 w-2 rounded-full",
          up && "bg-emerald-500",
          offline && "bg-rose-500",
          !up && !offline && "animate-pulse-soft bg-stone-400",
        )}
      />
      {up ? "fixpoint online" : offline ? "fixpoint offline" : "checking"}
    </div>
  );
}

const NAV_LINKS = [
  { to: "/", label: "Shop", end: true },
  { to: "/orders", label: "Orders" },
];

export function Layout() {
  const { cartCount, customer } = useShop();

  return (
    <div className="flex min-h-screen flex-col">
      <div className="bg-orange-600 px-4 py-2 text-center text-xs font-medium text-white">
        Free 30-day returns on every order · this is a demo storefront — refunds are settled and proven by the
        Fixpoint agent
      </div>

      <header className="sticky top-0 z-40 border-b border-stone-200 bg-white/90 backdrop-blur">
        <div className="mx-auto flex max-w-7xl flex-wrap items-center gap-x-8 gap-y-3 px-4 py-3.5">
          <Link to="/" className="flex items-center gap-3">
            <svg viewBox="0 0 64 64" className="h-10 w-10" aria-hidden="true">
              <rect width="64" height="64" rx="16" fill="#ea580c" />
              <path d="M19 26h26l-2.5 20h-21L19 26z" fill="#ffedd5" />
              <path
                d="M24 26a8 8 0 0 1 16 0"
                fill="none"
                stroke="#ffffff"
                strokeWidth="3.5"
                strokeLinecap="round"
              />
            </svg>
            <span>
              <span className="block font-display text-xl font-semibold leading-tight tracking-tight text-stone-900">
                Fixpoint Store
              </span>
              <span className="block text-xs text-stone-500">goods with agent-backed returns</span>
            </span>
          </Link>

          <nav aria-label="Store" className="flex items-center gap-1">
            {NAV_LINKS.map((link) => (
              <NavLink
                key={link.to}
                to={link.to}
                end={link.end}
                className={({ isActive }) =>
                  cn(
                    "rounded-full px-4 py-2 text-sm font-medium transition",
                    isActive
                      ? "bg-stone-900 text-white"
                      : "text-stone-600 hover:bg-stone-100 hover:text-stone-900",
                  )
                }
              >
                {link.label}
              </NavLink>
            ))}
          </nav>

          <div className="ml-auto flex flex-wrap items-center gap-2">
            <span
              className="hidden items-center gap-1.5 rounded-full border border-stone-200 bg-stone-50 px-3 py-1 text-xs text-stone-600 lg:inline-flex"
              title="The customer identity attached to orders and refund requests"
            >
              {customer.name} · {customer.email}
            </span>
            <FixpointStatus />
            <a
              href={CONSOLE_URL}
              target="_blank"
              rel="noopener noreferrer"
              className="hidden rounded-full px-3 py-1 text-xs font-medium text-stone-500 transition hover:bg-stone-100 hover:text-stone-900 sm:inline-flex"
            >
              Operator console ↗
            </a>
            <NavLink
              to="/cart"
              className={({ isActive }) =>
                cn(
                  "relative inline-flex items-center gap-2 rounded-full px-4 py-2 text-sm font-medium transition",
                  isActive ? "bg-orange-600 text-white" : "bg-stone-900 text-white hover:bg-stone-700",
                )
              }
            >
              <svg viewBox="0 0 24 24" className="h-4 w-4" fill="none" stroke="currentColor" strokeWidth="1.8">
                <path d="M6 8h12l-1.2 12H7.2L6 8z" strokeLinejoin="round" />
                <path d="M9 8a3 3 0 0 1 6 0" strokeLinecap="round" />
              </svg>
              Cart
              {cartCount > 0 && (
                <span className="absolute -right-1 -top-1 inline-flex min-w-[1.25rem] items-center justify-center rounded-full bg-orange-500 px-1.5 py-0.5 text-[11px] font-semibold text-white ring-2 ring-white">
                  {cartCount}
                </span>
              )}
            </NavLink>
          </div>
        </div>
      </header>

      <main className="mx-auto w-full max-w-7xl flex-1 px-4 py-8">
        <Outlet />
      </main>

      <footer className="border-t border-stone-200 bg-white px-4 py-6">
        <p className="mx-auto max-w-7xl text-xs leading-relaxed text-stone-500">
          Products and categories are served by the Platzi Fake Store API (shared and publicly mutable — used for
          display only). Orders and refund amounts are snapshotted locally; every refund request is handled by
          Fixpoint: the model proposes, deterministic code authorizes, a human approves money, and a verifier proves
          the outcome.
        </p>
      </footer>
    </div>
  );
}
