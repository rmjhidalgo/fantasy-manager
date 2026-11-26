import { useCallback, useEffect, useState } from "react";
import { api, type League, type Overview } from "./api";
import ImportPage from "./pages/ImportPage";
import OverviewPage from "./pages/OverviewPage";

type Tab = "overview" | "import";

type Health = { status: string; version: string; database: string };

export default function App() {
  const [tab, setTab] = useState<Tab>("overview");
  const [overview, setOverview] = useState<Overview | null>(null);
  const [leagues, setLeagues] = useState<League[]>([]);
  const [health, setHealth] = useState<Health | null>(null);
  const [backendDown, setBackendDown] = useState(false);

  const refresh = useCallback(() => {
    api
      .overview()
      .then((o) => {
        setOverview(o);
        setBackendDown(false);
      })
      .catch(() => setBackendDown(true));
    api.leagues().then((r) => setLeagues(r.leagues)).catch(() => {});
  }, []);

  useEffect(() => {
    refresh();
    fetch("/api/health")
      .then((r) => r.json())
      .then(setHealth)
      .catch(() => setBackendDown(true));
  }, [refresh]);

  const active = leagues.find((l) => l.active);

  return (
    <div className="min-h-screen">
      <header className="border-b border-slate-200 bg-white px-4 py-3 dark:border-slate-800 dark:bg-slate-900">
        <div className="mx-auto flex max-w-5xl flex-wrap items-center justify-between gap-3">
          <h1 className="text-lg font-semibold">🏀 Fantasy Manager</h1>
          {leagues.length > 0 && (
            <select
              value={active?.id ?? ""}
              onChange={(e) => api.setActiveLeague(Number(e.target.value)).then(refresh)}
              className="rounded-md border border-slate-300 bg-transparent px-2 py-1 text-sm dark:border-slate-700"
              title="Switch team"
            >
              {leagues.map((l) => (
                <option key={l.id} value={l.id}>
                  {l.my_team_name ?? "My team"} · {l.name ?? `League ${l.id}`}
                </option>
              ))}
            </select>
          )}
        </div>
        <nav className="mx-auto mt-3 flex max-w-5xl gap-1">
          {(
            [
              ["overview", "Overview"],
              ["import", "Import"],
            ] as [Tab, string][]
          ).map(([key, label]) => (
            <button
              key={key}
              onClick={() => setTab(key)}
              className={`rounded-md px-3 py-1.5 text-sm ${
                tab === key
                  ? "bg-slate-900 text-white dark:bg-slate-100 dark:text-slate-900"
                  : "text-slate-600 hover:bg-slate-100 dark:text-slate-300 dark:hover:bg-slate-800"
              }`}
            >
              {label}
            </button>
          ))}
        </nav>
      </header>

      <main className="mx-auto max-w-5xl px-4 py-6">
        {backendDown && (
          <p className="mb-4 rounded-md bg-red-50 p-3 text-red-700 dark:bg-red-950 dark:text-red-300">
            Can't reach the backend. Make sure it's running (start.bat starts both parts).
          </p>
        )}
        {tab === "overview" ? (
          <OverviewPage data={overview} onGoImport={() => setTab("import")} />
        ) : (
          <ImportPage onImported={refresh} />
        )}
      </main>

      <footer className="mx-auto max-w-5xl px-4 pb-6 text-xs text-slate-400">
        {health ? `v${health.version} · database ${health.database}` : ""}
      </footer>
    </div>
  );
}
