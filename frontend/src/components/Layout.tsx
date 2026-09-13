import { useEffect, useState } from "react";
import { NavLink, Outlet } from "react-router-dom";

import { useConfig } from "../api/hooks";
import { cn } from "../lib/cn";

function useHealth() {
  const [up, setUp] = useState<boolean | null>(null);

  useEffect(() => {
    let cancelled = false;
    const check = async () => {
      try {
        const response = await fetch("/health");
        if (!cancelled) setUp(response.ok);
      } catch {
        if (!cancelled) setUp(false);
      }
    };
    check();
    const timer = window.setInterval(check, 15_000);
    return () => {
      cancelled = true;
      window.clearInterval(timer);
    };
  }, []);

  return up;
}

const NAV_LINKS = [
  { to: "/", label: "Run Console", end: true },
  { to: "/evaluation", label: "Evaluation" },
  { to: "/runs", label: "Runs" },
  { to: "/about", label: "About" },
];

export function Layout() {
  const up = useHealth();
  const config = useConfig();
  const planner = config.data
    ? config.data.llm_enabled
      ? `llm${config.data.llm_model ? ` · ${config.data.llm_model}` : ""}`
      : "deterministic"
    : null;

  return (
    <div className="flex min-h-screen flex-col">
      <header className="sticky top-0 z-40 border-b border-slate-800/80 bg-slate-950/80 backdrop-blur">
        <div className="mx-auto flex max-w-[1500px] flex-wrap items-center gap-x-6 gap-y-3 px-4 py-3">
          <NavLink to="/" className="flex items-center gap-3">
            <svg viewBox="0 0 64 64" className="h-9 w-9" aria-hidden="true">
              <rect width="64" height="64" rx="14" fill="#4f46e5" />
              <circle cx="32" cy="32" r="17" fill="none" stroke="#c7d2fe" strokeWidth="3" opacity="0.9" />
              <circle cx="32" cy="32" r="6.5" fill="#ffffff" />
              <circle cx="49" cy="15" r="4" fill="#34d399" />
            </svg>
            <span>
              <span className="block text-lg font-semibold leading-tight text-white">Fixpoint</span>
              <span className="block text-xs text-slate-400">Run console &amp; evaluation dashboard</span>
            </span>
          </NavLink>

          <nav aria-label="Main" className="order-3 flex w-full gap-1 overflow-x-auto sm:order-none sm:w-auto">
            {NAV_LINKS.map((link) => (
              <NavLink
                key={link.to}
                to={link.to}
                end={link.end}
                className={({ isActive }) =>
                  cn(
                    "whitespace-nowrap rounded-lg px-3 py-1.5 text-sm font-medium transition",
                    isActive ? "bg-indigo-600/20 text-indigo-200" : "text-slate-300 hover:bg-slate-800/70 hover:text-white",
                  )
                }
              >
                {link.label}
              </NavLink>
            ))}
            <a
              href="/docs"
              target="_blank"
              rel="noopener noreferrer"
              className="whitespace-nowrap rounded-lg px-3 py-1.5 text-sm font-medium text-slate-400 transition hover:bg-slate-800/70 hover:text-white"
            >
              API Docs
            </a>
          </nav>

          <div className="ml-auto flex items-center gap-2">
            {planner && (
              <div
                className={cn(
                  "flex items-center gap-2 rounded-full border px-3 py-1 text-xs font-medium",
                  config.data?.llm_enabled
                    ? "border-indigo-500/40 bg-indigo-500/10 text-indigo-200"
                    : "border-slate-700 text-slate-400",
                )}
                title="Active planner: LLM (with deterministic fallback) or deterministic"
              >
                planner: {planner}
              </div>
            )}
            <div
              className={cn(
                "flex items-center gap-2 rounded-full border px-3 py-1 text-xs font-medium",
                up === null && "border-slate-700 text-slate-400",
                up === true && "border-emerald-500/40 bg-emerald-500/10 text-emerald-300",
                up === false && "border-rose-500/40 bg-rose-500/10 text-rose-300",
              )}
            >
              <span
                className={cn(
                  "h-2 w-2 rounded-full",
                  up === null && "animate-pulse-soft bg-slate-500",
                  up === true && "bg-emerald-400",
                  up === false && "bg-rose-400",
                )}
              />
              {up === null ? "checking" : up ? "control plane up" : "offline"}
            </div>
          </div>
        </div>
      </header>

      <main className="mx-auto w-full max-w-[1500px] flex-1 px-4 py-6">
        <Outlet />
      </main>

      <footer className="border-t border-slate-800/80 px-4 py-5">
        <p className="mx-auto max-w-[1500px] text-xs text-slate-500">
          Fixpoint — the model proposes, deterministic code authorizes, a human approves money, and an independent
          verifier confirms the outcome before anything is claimed.
        </p>
      </footer>
    </div>
  );
}
