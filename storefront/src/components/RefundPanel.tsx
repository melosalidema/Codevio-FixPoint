import { useEffect, useMemo, useState } from "react";
import { useMutation, useQueryClient } from "@tanstack/react-query";

import { usd } from "../lib/format";
import { notifyRefundRequested } from "../lib/formspree";
import { describeRun, fixpoint, isRefundSettled, runUrl, type RunDetail } from "../lib/fixpoint";
import { useFixpointConfig, useRun } from "../lib/hooks";
import { refundableItems, type Order, type OrderItem } from "../lib/orders";
import { buildRefundRequestText, reasonByValue, REFUND_REASONS } from "../lib/refund";
import { useShop } from "../state/ShopContext";
import { ProductImage, Spinner, StatusPill } from "./Ui";

function isFinal(run: RunDetail | undefined): boolean {
  if (!run) return false;
  return run.status !== "awaiting_approval" && run.status !== "pending";
}

function RunStatusCard({
  run,
  loading,
  onRefresh,
}: {
  run: RunDetail | undefined;
  loading: boolean;
  onRefresh: () => void;
}) {
  const view = run ? describeRun(run) : null;

  return (
    <div className="space-y-3 rounded-2xl border border-stone-200 bg-stone-50 p-4">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <StatusPill tone={view?.tone ?? "neutral"}>
          {!run && loading ? (
            <>
              <Spinner className="h-3 w-3" /> Submitting refund run…
            </>
          ) : (
            (view?.title ?? "Refund run")
          )}
        </StatusPill>
        <div className="flex items-center gap-2">
          {run && <span className="code">{run.run_id.slice(0, 12)}…</span>}
          <button
            type="button"
            className="text-xs font-medium text-stone-400 transition hover:text-stone-900"
            onClick={onRefresh}
          >
            Refresh
          </button>
        </div>
      </div>

      {view && <p className="text-sm leading-relaxed text-stone-600">{view.detail}</p>}

      {run?.report?.report_text && (
        <p className="rounded-xl border border-stone-200 bg-white p-3.5 text-xs leading-relaxed text-stone-500">
          {run.report.report_text}
        </p>
      )}

      {run && (
        <div className="flex flex-wrap gap-1.5 text-xs">
          <span className="rounded-full border border-stone-200 bg-white px-2.5 py-1 text-stone-600">
            {run.verified ? "verified" : `status: ${run.status}`}
          </span>
          {run.audit && (
            <span className="rounded-full border border-stone-200 bg-white px-2.5 py-1 text-stone-600">
              audit chain {run.audit.chain_ok ? "intact" : "broken"}
            </span>
          )}
          {run.planner_source && (
            <span className="rounded-full border border-stone-200 bg-white px-2.5 py-1 text-stone-600">
              planner: {run.planner_source}
            </span>
          )}
          {run.approval_artifact && (
            <span className="rounded-full border border-stone-200 bg-white px-2.5 py-1 text-stone-600">
              approval role: {run.approval_artifact.required_role}
            </span>
          )}
        </div>
      )}

      {run?.status === "awaiting_approval" && run.unsafe_blocked === 0 && (
        <div className="rounded-xl border border-amber-200 bg-amber-50 p-3.5 text-xs leading-relaxed text-amber-800">
          A human must approve this refund in the Fixpoint console (role <span className="code">team_lead</span>).{" "}
          <a href={runUrl(run.run_id)} target="_blank" rel="noopener noreferrer" className="font-medium underline">
            Open the run ↗
          </a>{" "}
          — this page refreshes automatically.
        </div>
      )}

      {run?.unsafe_blocked ? (
        <div className="rounded-xl border border-rose-200 bg-rose-50 p-3.5 text-xs leading-relaxed text-rose-700">
          The gateway blocked this action as unsafe; zero money moved. The escalation is waiting for a human in the{" "}
          <a href={runUrl(run.run_id)} target="_blank" rel="noopener noreferrer" className="font-medium underline">
            Fixpoint console ↗
          </a>
          .
        </div>
      ) : null}

      {run?.verification && run.verification.checks.length > 0 && (
        <details className="text-xs text-stone-500">
          <summary className="cursor-pointer select-none font-medium">
            Verifier checks ({run.verification.checks.filter((check) => check.passed).length}/
            {run.verification.checks.length} passed)
          </summary>
          <ul className="mt-2 space-y-1">
            {run.verification.checks.map((check) => (
              <li key={check.name} className="flex items-start gap-2">
                <span className={check.passed ? "text-emerald-600" : "text-rose-600"}>
                  {check.passed ? "✓" : "✗"}
                </span>
                <span>
                  <span className="text-stone-700">{check.name}</span>
                  {check.detail ? <span className="text-stone-400"> — {check.detail}</span> : null}
                </span>
              </li>
            ))}
          </ul>
        </details>
      )}
    </div>
  );
}

function ItemCheckbox({
  item,
  checked,
  onToggle,
}: {
  item: OrderItem;
  checked: boolean;
  onToggle: () => void;
}) {
  const refunded = Boolean(item.refundedAt);
  return (
    <label
      className={
        refunded
          ? "flex cursor-not-allowed items-center gap-3 rounded-xl border border-stone-200 bg-stone-50 p-2.5 opacity-60"
          : "flex cursor-pointer items-center gap-3 rounded-xl border border-stone-200 bg-white p-2.5 transition hover:border-stone-300 has-[:checked]:border-orange-400 has-[:checked]:bg-orange-50/60"
      }
    >
      <input
        type="checkbox"
        className="h-4 w-4 accent-orange-600"
        checked={checked}
        disabled={refunded}
        onChange={onToggle}
      />
      <span className="h-11 w-11 shrink-0 overflow-hidden rounded-lg bg-stone-100">
        <ProductImage src={item.image} title={item.title} />
      </span>
      <span className="min-w-0 flex-1">
        <span className="block truncate text-sm font-medium text-stone-800">{item.title}</span>
        <span className="block text-xs text-stone-500">
          {usd(item.priceCents)} × {item.quantity}
        </span>
      </span>
      <span className="text-sm font-semibold text-stone-900">{usd(item.priceCents * item.quantity)}</span>
      {refunded && (
        <StatusPill tone="success">
          <span className="whitespace-nowrap">refunded</span>
        </StatusPill>
      )}
    </label>
  );
}

export function RefundPanel({ order }: { order: Order }) {
  const { addRefund, markRefunded } = useShop();
  const queryClient = useQueryClient();
  const config = useFixpointConfig();

  const refundable = useMemo(() => refundableItems(order), [order]);
  const active = order.refunds.length > 0 ? order.refunds[order.refunds.length - 1] : undefined;
  const runQuery = useRun(active?.runId);
  const run = runQuery.data;
  const awaiting = Boolean(active) && !isFinal(run);
  const showForm = refundable.length > 0 && !awaiting;

  const [selected, setSelected] = useState<string[]>([]);
  const refundableKey = refundable.map((item) => item.id).join("|");
  useEffect(() => {
    setSelected(refundable.map((item) => item.id));
  }, [refundableKey]);

  useEffect(() => {
    if (active && isRefundSettled(run)) {
      markRefunded(order.id, active.itemIds);
    }
  }, [active, run, order.id, markRefunded]);

  const [reason, setReason] = useState(REFUND_REASONS[0].value);
  const [note, setNote] = useState("");
  const [stripeFailures, setStripeFailures] = useState(0);
  const [injectInstruction, setInjectInstruction] = useState(false);
  const [duplicateCustomer, setDuplicateCustomer] = useState(false);
  const [error, setError] = useState("");
  const [notification, setNotification] = useState<"idle" | "sending" | "sent" | "failed">("idle");
  const [notificationError, setNotificationError] = useState("");

  const selectedItems = order.items.filter((item) => selected.includes(item.id) && !item.refundedAt);
  const totalCents = selectedItems.reduce((sum, item) => sum + item.priceCents * item.quantity, 0);
  const reasonOption = reasonByValue(reason);

  const preview = buildRefundRequestText({
    order,
    items: selectedItems,
    reason: reasonOption,
    note,
    totalCents,
    injectInstruction,
  });

  const mutation = useMutation({
    mutationFn: () =>
      fixpoint.createRefundRun({
        requestText: preview,
        amountCents: totalCents,
        stripeRefundFailures: stripeFailures,
        duplicateCustomer,
      }),
    onSuccess: (created) => {
      queryClient.setQueryData(["fixpoint", "run", created.run_id], created);
      addRefund(order.id, {
        runId: created.run_id,
        itemIds: selectedItems.map((item) => item.id),
        submittedAt: new Date().toISOString(),
      });
      setError("");
      setNote("");
    },
    onError: (mutationError) => {
      setError(mutationError instanceof Error ? mutationError.message : "Could not submit the refund request.");
    },
  });

  const envelope = config.data?.envelope;

  return (
    <section className="panel">
      <div className="panel-head">
        <h2 className="panel-title">Refunds</h2>
        {envelope && (
          <span className="text-xs text-stone-400">
            auto up to {usd(envelope.auto_approve_cents)} · bigger amounts pause for a human · cap{" "}
            {usd(envelope.max_refund_cents)}
          </span>
        )}
      </div>

      <div className="space-y-5 p-5">
        {active && <RunStatusCard run={run} loading={runQuery.isFetching} onRefresh={() => void runQuery.refetch()} />}

        {refundable.length === 0 && !active && (
          <p className="rounded-xl border border-emerald-200 bg-emerald-50 p-3.5 text-sm text-emerald-800">
            Every item in this order has been refunded and verified.
          </p>
        )}

        {refundable.length === 0 && active && isRefundSettled(run) && (
          <p className="rounded-xl border border-emerald-200 bg-emerald-50 p-3.5 text-sm text-emerald-800">
            Every item in this order has been refunded and verified.
          </p>
        )}

        {showForm && (
          <form
            className="space-y-5"
            onSubmit={(event) => {
              event.preventDefault();
              if (selectedItems.length === 0) {
                setError("Select at least one item to refund.");
                return;
              }
              if (totalCents <= 0) {
                setError("The refund total must be greater than zero.");
                return;
              }
              setError("");
              // Email the support mailbox via Formspree (independent of the
              // agent run): a failed notification must not block the refund.
              setNotification("sending");
              setNotificationError("");
              void notifyRefundRequested({
                order,
                items: selectedItems,
                reason: reasonOption,
                note,
                totalCents,
                requestText: preview,
              }).then((result) => {
                if (result.ok) {
                  setNotification("sent");
                } else {
                  setNotification("failed");
                  setNotificationError(result.error);
                }
              });
              mutation.mutate();
            }}
          >
            <div>
              <p className="mb-2 text-xs font-medium uppercase tracking-wider text-stone-500">Items to refund</p>
              <div className="space-y-2">
                {order.items.map((item) => (
                  <ItemCheckbox
                    key={item.id}
                    item={item}
                    checked={selected.includes(item.id) && !item.refundedAt}
                    onToggle={() =>
                      setSelected((current) =>
                        current.includes(item.id)
                          ? current.filter((id) => id !== item.id)
                          : [...current, item.id],
                      )
                    }
                  />
                ))}
              </div>
            </div>

            <div className="grid gap-4 sm:grid-cols-2">
              <div>
                <label
                  htmlFor="refund-reason"
                  className="mb-1.5 block text-xs font-medium uppercase tracking-wider text-stone-500"
                >
                  Reason
                </label>
                <select
                  id="refund-reason"
                  className="input"
                  value={reason}
                  onChange={(event) => setReason(event.target.value)}
                >
                  {REFUND_REASONS.map((option) => (
                    <option key={option.value} value={option.value}>
                      {option.label}
                    </option>
                  ))}
                </select>
              </div>
              <div>
                <label
                  htmlFor="refund-note"
                  className="mb-1.5 block text-xs font-medium uppercase tracking-wider text-stone-500"
                >
                  Note (optional)
                </label>
                <input
                  id="refund-note"
                  className="input"
                  value={note}
                  onChange={(event) => setNote(event.target.value)}
                  placeholder="e.g. the box arrived crushed"
                  maxLength={300}
                />
              </div>
            </div>

            <details className="rounded-xl border border-stone-200 bg-stone-50 p-3.5">
              <summary className="cursor-pointer select-none text-xs font-medium uppercase tracking-wider text-stone-500">
                Test hooks (Fixpoint demo)
              </summary>
              <div className="mt-3 space-y-3 text-sm text-stone-700">
                <label className="flex items-center gap-2.5">
                  <input
                    type="checkbox"
                    className="h-4 w-4 accent-orange-600"
                    checked={injectInstruction}
                    onChange={(event) => setInjectInstruction(event.target.checked)}
                  />
                  Append a suspicious instruction (prompt-injection test)
                </label>
                <label className="flex items-center gap-2.5">
                  <input
                    type="checkbox"
                    className="h-4 w-4 accent-orange-600"
                    checked={duplicateCustomer}
                    onChange={(event) => setDuplicateCustomer(event.target.checked)}
                  />
                  Simulate duplicate customer records (ambiguity test)
                </label>
                <label className="flex items-center gap-2.5">
                  Stripe refund failures
                  <input
                    type="number"
                    min={0}
                    max={5}
                    className="input w-20"
                    value={stripeFailures}
                    onChange={(event) =>
                      setStripeFailures(Math.min(5, Math.max(0, Number(event.target.value) || 0)))
                    }
                  />
                  <span className="text-xs text-stone-400">retries with the same idempotency key</span>
                </label>
              </div>
            </details>

            <details className="rounded-xl border border-stone-200 bg-stone-50 p-3.5">
              <summary className="cursor-pointer select-none text-xs font-medium uppercase tracking-wider text-stone-500">
                Preview the request Fixpoint will receive
              </summary>
              <pre className="mt-3 whitespace-pre-wrap rounded-xl bg-stone-900 p-3.5 font-mono text-xs leading-relaxed text-stone-100">
                {preview || "Select items to build the request."}
              </pre>
            </details>

            {error && <p className="text-sm text-rose-600">{error}</p>}

            <div className="flex flex-wrap items-center gap-3">
              <button
                type="submit"
                className="btn-accent"
                disabled={mutation.isPending || selectedItems.length === 0}
              >
                {mutation.isPending && <Spinner className="h-4 w-4" />}
                Submit refund request · {usd(totalCents)}
              </button>
              <p className="max-w-sm text-xs leading-relaxed text-stone-400">
                The agent investigates, clamps the amount to policy, and either refunds automatically (small amounts)
                or pauses for a human.
              </p>
            </div>

            {notification === "sending" && (
              <p className="text-xs text-stone-400">Emailing the support notification…</p>
            )}
            {notification === "sent" && (
              <p className="text-xs text-emerald-700">Refund notification emailed to the support inbox.</p>
            )}
            {notification === "failed" && (
              <p className="text-xs text-amber-700">
                Refund submitted, but the support notification could not be sent ({notificationError}).
              </p>
            )}
          </form>
        )}

        {awaiting && !run && (
          <p className="text-xs text-stone-400">
            Waiting for the run to be persisted… If this persists, check that the Fixpoint backend is running.
          </p>
        )}
      </div>
    </section>
  );
}
