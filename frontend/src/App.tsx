import { useEffect, useState } from "react";

type Health = {
  status: string;
  version: string;
  database: string;
  data_dir: string;
};

type State =
  | { kind: "loading" }
  | { kind: "ok"; health: Health }
  | { kind: "error"; message: string };

// Screens planned for later milestones (PLAN.md §9).
const COMING_SOON = [
  "Import",
  "Dashboard",
  "Matchup",
  "Lineup",
  "Free agents",
  "Suggested moves",
  "Trades",
];

export default function App() {
  const [state, setState] = useState<State>({ kind: "loading" });

  const check = () => {
    setState({ kind: "loading" });
    fetch("/api/health")
      .then((r) => {
        if (!r.ok) throw new Error(`Backend replied ${r.status}`);
        return r.json() as Promise<Health>;
      })
      .then((health) => setState({ kind: "ok", health }))
      .catch((e: unknown) =>
        setState({ kind: "error", message: e instanceof Error ? e.message : String(e) }),
      );
  };

  useEffect(check, []);

  return (
    <div className="min-h-screen">
      <header className="border-b border-slate-200 bg-white px-4 py-3 dark:border-slate-800 dark:bg-slate-900">
        <div className="mx-auto flex max-w-5xl items-center justify-between">
          <h1 className="text-lg font-semibold">🏀 Fantasy Manager</h1>
          <span className="text-sm text-slate-500">
            {state.kind === "ok" ? `v${state.health.version}` : ""}
          </span>
        </div>
      </header>

      <main className="mx-auto max-w-5xl space-y-6 px-4 py-6">
        <section className="rounded-lg border border-slate-200 bg-white p-5 dark:border-slate-800 dark:bg-slate-900">
          <div className="mb-4 flex items-center justify-between">
            <h2 className="font-semibold">Setup check</h2>
            <button
              onClick={check}
              className="rounded-md border border-slate-300 px-3 py-1 text-sm hover:bg-slate-100 dark:border-slate-700 dark:hover:bg-slate-800"
            >
              Check again
            </button>
          </div>

          {state.kind === "loading" && <p className="text-slate-500">Checking…</p>}

          {state.kind === "error" && (
            <div className="text-red-600 dark:text-red-400">
              <p className="font-medium">Can't reach the backend.</p>
              <p className="text-sm">
                {state.message}. Make sure it's running (start.bat starts both parts).
              </p>
            </div>
          )}

          {state.kind === "ok" && (
            <ul className="space-y-2 text-sm">
              <StatusRow label="Backend" ok={state.health.status === "ok"} />
              <StatusRow label="Database" ok={state.health.database === "ok"} />
              <li className="flex justify-between gap-4">
                <span>Data folder</span>
                <code className="truncate text-slate-500">{state.health.data_dir}</code>
              </li>
            </ul>
          )}
        </section>

        <section className="rounded-lg border border-dashed border-slate-300 p-5 dark:border-slate-700">
          <h2 className="mb-2 font-semibold">Coming next</h2>
          <p className="mb-3 text-sm text-slate-500">
            These screens are built in the next milestones. Milestone 1 starts with importing your
            saved Yahoo pages.
          </p>
          <div className="flex flex-wrap gap-2">
            {COMING_SOON.map((name) => (
              <span
                key={name}
                className="rounded-full bg-slate-100 px-3 py-1 text-sm text-slate-600 dark:bg-slate-800 dark:text-slate-300"
              >
                {name}
              </span>
            ))}
          </div>
        </section>
      </main>
    </div>
  );
}

function StatusRow({ label, ok }: { label: string; ok: boolean }) {
  return (
    <li className="flex justify-between">
      <span>{label}</span>
      <span className={ok ? "text-green-600 dark:text-green-400" : "text-red-600 dark:text-red-400"}>
        {ok ? "✓ OK" : "✗ Problem"}
      </span>
    </li>
  );
}
