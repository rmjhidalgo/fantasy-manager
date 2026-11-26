// Small shared UI pieces.
import type { ReactNode } from "react";

export const card = "rounded-lg border border-slate-200 bg-white p-4 dark:border-slate-800 dark:bg-slate-900";
export const select = "rounded-md border border-slate-300 bg-transparent px-2 py-1 text-sm dark:border-slate-700 dark:bg-slate-900";
export const btn = "rounded-md bg-blue-600 px-3 py-1.5 text-sm text-white hover:bg-blue-700 disabled:opacity-50";

export function dayLabel(iso: string): string {
  const d = new Date(iso + "T12:00:00");
  return d.toLocaleDateString([], { weekday: "short", month: "numeric", day: "numeric" });
}

export function shortDay(iso: string): string {
  return new Date(iso + "T12:00:00").toLocaleDateString([], { weekday: "short" });
}

export function StatusTag({ status }: { status: string | null | undefined }) {
  if (!status) return null;
  return (
    <span className="ml-1 rounded bg-red-100 px-1 text-xs font-medium text-red-700 dark:bg-red-950 dark:text-red-300">{status}</span>
  );
}

export function YahooLink({
  href,
  children = "Open on Yahoo ↗",
  onOpen,
}: {
  href: string;
  children?: ReactNode;
  onOpen?: () => void; // e.g. record the move in the move log
}) {
  return (
    <a
      href={href}
      target="_blank"
      rel="noreferrer"
      onClick={onOpen}
      onAuxClick={onOpen}
      className="whitespace-nowrap text-sm text-violet-700 hover:underline dark:text-violet-300"
    >
      {children}
    </a>
  );
}

export function Notice({ tone = "info", children }: { tone?: "info" | "warn" | "ok"; children: ReactNode }) {
  const tones = {
    info: "bg-slate-50 text-slate-700 dark:bg-slate-800 dark:text-slate-200",
    warn: "bg-amber-50 text-amber-900 dark:bg-amber-950 dark:text-amber-200",
    ok: "bg-green-50 text-green-800 dark:bg-green-950 dark:text-green-300",
  };
  return <div className={`rounded-md p-3 text-sm ${tones[tone]}`}>{children}</div>;
}

export function Loading({ error }: { error?: string | null }) {
  return error ? <p className="text-sm text-red-600 dark:text-red-400">{error}</p> : <p className="text-slate-500">Loading…</p>;
}

export function errText(e: unknown): string {
  return e instanceof Error ? e.message : String(e);
}
