import { useCallback, useEffect, useState } from "react";
import { notifyNew } from "./alerts";
import { api, type AlertItem, type League, type Outlook, type Overview } from "./api";
import FreeAgentsPage from "./pages/FreeAgentsPage";
import ImportPage from "./pages/ImportPage";
import LineupPage from "./pages/LineupPage";
import MatchupPage from "./pages/MatchupPage";
import OverviewPage, { type NavTarget } from "./pages/OverviewPage";
import MovesPage from "./pages/MovesPage";
import SettingsPage from "./pages/SettingsPage";
import StrategyPage from "./pages/StrategyPage";
import StreamingPage from "./pages/StreamingPage";
import SuggestPage from "./pages/SuggestPage";

type Tab = "overview" | NavTarget;

const TABS: [Tab, string][] = [
  ["overview", "Overview"],
  ["suggest", "Suggested moves"],
  ["matchup", "Matchup"],
  ["lineup", "Lineup"],
  ["free-agents", "Free agents"],
  ["streaming", "Streaming"],
  ["strategy", "Strategy"],
  ["moves", "Move log"],
  ["import", "Import & data"],
  ["settings", "Settings"],
];

const ALERTS_EVERY_MS = 5 * 60 * 1000;

type Health = { status: string; version: string; database: string };

export default function App() {
  const [tab, setTab] = useState<Tab>("overview");
  const [overview, setOverview] = useState<Overview | null>(null);
  const [outlook, setOutlook] = useState<Outlook | null>(null);
  const [alerts, setAlerts] = useState<AlertItem[] | null>(null);
  const [leagues, setLeagues] = useState<League[]>([]);
  const [health, setHealth] = useState<Health | null>(null);
  const [backendDown, setBackendDown] = useState(false);
  const [version, setVersion] = useState(0); // bumps when data changes, so pages reload
  const [askClaude, setAskClaude] = useState(false);

  const loadAssistant = useCallback(() => {
    api
      .assistant()
      .then((s) => setAskClaude(s.enabled && s.installed))
      .catch(() => setAskClaude(false));
  }, []);
  useEffect(loadAssistant, [loadAssistant]);

  const loadAlerts = useCallback(() => {
    api
      .alerts()
      .then((r) => {
        setAlerts(r.alerts);
        notifyNew(r.alerts, (a) => a.action && setTab(a.action));
      })
      .catch(() => setAlerts(null));
  }, []);

  const refresh = useCallback(() => {
    api
      .overview()
      .then((o) => {
        setOverview(o);
        setBackendDown(false);
      })
      .catch(() => setBackendDown(true));
    api.leagues().then((r) => setLeagues(r.leagues)).catch(() => {});
    api
      .outlook()
      .then(setOutlook)
      .catch(() => setOutlook(null)); // no league yet, or no NBA data yet
    loadAlerts();
    setVersion((v) => v + 1);
  }, [loadAlerts]);

  useEffect(() => {
    refresh();
    fetch("/api/health")
      .then((r) => r.json())
      .then(setHealth)
      .catch(() => setBackendDown(true));
    const t = setInterval(loadAlerts, ALERTS_EVERY_MS);
    return () => clearInterval(t);
  }, [refresh, loadAlerts]);

  const active = leagues.find((l) => l.active);
  const urgent = alerts?.filter((a) => a.level !== "info").length ?? 0;

  return (
    <div className="min-h-screen">
      <header className="border-b border-slate-200 bg-white px-4 py-3 dark:border-slate-800 dark:bg-slate-900">
        <div className="mx-auto flex max-w-6xl flex-wrap items-center justify-between gap-3">
          <h1 className="text-lg font-semibold">🏀 Fantasy Manager</h1>
          <div className="flex flex-wrap items-center gap-3">
            {askClaude && (
              <a
                href="claude://"
                title="Opens Claude Desktop, which can read this app's numbers (read-only)"
                className="rounded-md border border-violet-300 px-2 py-1 text-sm text-violet-700 hover:bg-violet-50 dark:border-violet-700 dark:text-violet-300 dark:hover:bg-violet-950"
              >
                ✦ Ask Claude
              </a>
            )}
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
        </div>
        <nav className="mx-auto mt-3 flex max-w-6xl flex-wrap gap-1">
          {TABS.map(([key, label]) => (
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
              {key === "overview" && urgent > 0 && (
                <span className="ml-1.5 rounded-full bg-red-600 px-1.5 text-xs text-white">{urgent}</span>
              )}
            </button>
          ))}
        </nav>
      </header>

      <main className="mx-auto max-w-6xl px-4 py-6">
        {backendDown && (
          <p className="mb-4 rounded-md bg-red-50 p-3 text-red-700 dark:bg-red-950 dark:text-red-300">
            Can't reach the backend. Make sure it's running (start.bat starts both parts).
          </p>
        )}
        {tab === "overview" && <OverviewPage data={overview} outlook={outlook} alerts={alerts} onNavigate={setTab} />}
        {tab === "suggest" && <SuggestPage key={version} outlook={outlook} />}
        {tab === "matchup" && <MatchupPage version={version} />}
        {tab === "lineup" && <LineupPage outlook={outlook} />}
        {tab === "free-agents" && <FreeAgentsPage key={version} />}
        {tab === "streaming" && <StreamingPage key={version} />}
        {tab === "strategy" && <StrategyPage key={version} />}
        {tab === "moves" && <MovesPage key={version} />}
        {tab === "import" && <ImportPage onImported={refresh} />}
        {tab === "settings" && <SettingsPage onChange={loadAssistant} />}
      </main>

      <footer className="mx-auto max-w-6xl px-4 pb-6 text-xs text-slate-400">
        {health ? `v${health.version} · database ${health.database}` : ""}
      </footer>
    </div>
  );
}
