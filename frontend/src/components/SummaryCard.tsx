import { useState } from "react";
import type { DailySummary } from "../api";
import { card } from "../ui";

const DOT = { info: "bg-slate-400", warn: "bg-amber-500", danger: "bg-red-500" };

export default function SummaryCard({
  summary,
  onAction,
}: {
  summary: DailySummary | null;
  onAction: (action: string) => void;
}) {
  const [open, setOpen] = useState(true);
  if (!summary || summary.items.length === 0) return null;
  return (
    <section className={card}>
      <button onClick={() => setOpen(!open)} className="flex w-full items-center justify-between text-left">
        <h2 className="font-semibold">☀ Today's summary</h2>
        <span className="text-xs text-slate-500">{open ? "Hide" : "Show"}</span>
      </button>
      {open && (
        <ul className="mt-3 space-y-2 text-sm">
          {summary.items.map((i, k) => (
            <li key={k} className="flex items-start gap-2">
              <span className={`mt-1.5 inline-block h-2 w-2 shrink-0 rounded-full ${DOT[i.level]}`} />
              <div className="flex-1">
                <span className="font-medium">{i.title}</span>
                {i.detail && <span className="text-slate-600 dark:text-slate-300"> — {i.detail}</span>}
              </div>
              {i.action && (
                <button onClick={() => onAction(i.action!)} className="shrink-0 text-xs text-blue-700 hover:underline dark:text-blue-300">
                  Open →
                </button>
              )}
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}
