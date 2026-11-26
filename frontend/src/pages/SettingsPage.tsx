import { useCallback, useEffect, useState } from "react";
import { api, type AssistantStatus, type Horizon, type SummarySettings, type Tuning } from "../api";
import { formatWhen, hoursOld } from "../time";
import { btn, card, errText, Loading, Notice, select } from "../ui";

function SummarySettingsCard() {
  const [s, setS] = useState<SummarySettings | null>(null);
  const [saved, setSaved] = useState(false);
  useEffect(() => {
    api
      .summarySettings()
      .then(setS)
      .catch(() => {});
  }, []);
  if (!s) return null;
  const save = (next: SummarySettings) => {
    setS(next);
    api
      .setSummarySettings(next)
      .then((r) => {
        setS(r);
        setSaved(true);
        setTimeout(() => setSaved(false), 1500);
      })
      .catch(() => {});
  };
  return (
    <section className={card}>
      <h2 className="mb-1 font-semibold">Daily summary</h2>
      <p className="mb-3 text-sm text-slate-500">
        A short summary at the top of Overview: pages to re-save, lineup fixes, injuries, best moves, matchup and playoff chances.
        At your chosen time each day you also get a desktop notification, while the app is open in a browser tab (turn on
        notifications on the Alerts card).
      </p>
      <div className="flex flex-wrap items-center gap-4 text-sm">
        <label className="flex items-center gap-2">
          <input type="checkbox" checked={s.enabled} onChange={(e) => save({ ...s, enabled: e.target.checked })} /> Notify me daily at
        </label>
        <input
          type="time"
          value={s.time}
          onChange={(e) => e.target.value && save({ ...s, time: e.target.value })}
          className="rounded-md border border-slate-300 bg-transparent px-2 py-1 dark:border-slate-700"
        />
        <label className="flex items-center gap-2">
          <span className="text-slate-500">Moves for</span>
          <select value={s.horizon} onChange={(e) => save({ ...s, horizon: e.target.value as Horizon })} className={select}>
            <option value="A">A · this week</option>
            <option value="B">B · next week</option>
            <option value="C">C · next 5 weeks</option>
            <option value="D">D · playoffs</option>
          </select>
        </label>
        {saved && <span className="text-green-700 dark:text-green-400">Saved</span>}
      </div>
    </section>
  );
}

function TuningCard({ onChange }: { onChange: () => void }) {
  const [t, setT] = useState<Tuning | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const run = () => {
    setBusy(true);
    setError(null);
    api
      .tuning()
      .then(setT)
      .catch((e) => setError(errText(e)))
      .finally(() => setBusy(false));
  };
  const apply = (w: number[] | null) => {
    setBusy(true);
    api
      .setTuning(w)
      .then(() => {
        onChange();
        run();
      })
      .catch((e) => {
        setError(errText(e));
        setBusy(false);
      });
  };
  const same = (a: number[], b: number[]) => a.length === b.length && a.every((x, i) => Math.abs(x - b[i]) < 1e-9);
  return (
    <section className={card}>
      <h2 className="mb-1 font-semibold">Projection tuning</h2>
      <p className="mb-3 text-sm text-slate-500">
        Learns from real results: for every game in the last 3 weeks, it projects each player the way the app would have the day
        before, and checks which mix of recent and season-long form missed least.
      </p>
      <button className={btn} disabled={busy} onClick={run}>
        {busy ? "Testing…" : t ? "Test again" : "Test projection mixes"}
      </button>
      {error && <p className="mt-2 text-sm text-red-600 dark:text-red-400">{error}</p>}
      {t && (
        <div className="mt-3 space-y-2">
          <table className="w-full text-sm">
            <thead className="text-left text-slate-500">
              <tr>
                <th className="py-1 pr-2 font-medium">Mix</th>
                {t.windows.map((w) => (
                  <th key={w} className="py-1 pr-2 text-right font-medium">
                    {w}
                  </th>
                ))}
                <th className="py-1 pr-2 text-right font-medium">Avg. miss</th>
                <th className="py-1 font-medium"></th>
              </tr>
            </thead>
            <tbody>
              {t.results.map((r, i) => {
                const inUse = same(r.weights, t.current);
                return (
                  <tr key={r.name} className={`border-t border-slate-100 dark:border-slate-800 ${inUse ? "font-medium" : ""}`}>
                    <td className="py-1 pr-2">
                      {r.name}
                      {i === 0 && <span className="ml-1 text-xs text-green-700 dark:text-green-400">best</span>}
                    </td>
                    {r.weights.map((w, k) => (
                      <td key={k} className="py-1 pr-2 text-right tabular-nums text-slate-500">
                        {Math.round(w * 100)}%
                      </td>
                    ))}
                    <td className="py-1 pr-2 text-right tabular-nums">{r.mae?.toFixed(2) ?? "–"} FP</td>
                    <td className="py-1 text-right text-xs">
                      {inUse ? (
                        <span className="text-slate-500">in use</span>
                      ) : (
                        <button className="text-blue-700 hover:underline dark:text-blue-300" disabled={busy} onClick={() => apply(r.weights)}>
                          Use
                        </button>
                      )}
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
          <p className="text-sm">
            {t.recommend && t.best
              ? `"${t.best.name}" would have missed less: consider using it.`
              : "The mix in use is as good as the alternatives (within 1%): no change needed."}{" "}
            <span className="text-slate-500">Tested on {t.games_tested.toLocaleString()} games.</span>
          </p>
          {!same(t.current, [0.15, 0.25, 0.3, 0.3]) && (
            <button className="text-sm text-slate-500 hover:underline" disabled={busy} onClick={() => apply(null)}>
              Back to the standard mix
            </button>
          )}
        </div>
      )}
    </section>
  );
}

function CopyBox({ text }: { text: string }) {
  const [copied, setCopied] = useState(false);
  return (
    <div className="relative">
      <pre className="overflow-x-auto rounded-md bg-slate-100 p-3 pr-16 text-xs dark:bg-slate-800">{text}</pre>
      <button
        onClick={() =>
          navigator.clipboard
            ?.writeText(text)
            .then(() => {
              setCopied(true);
              setTimeout(() => setCopied(false), 1500);
            })
            .catch(() => {})
        }
        className="absolute right-2 top-2 rounded border border-slate-300 bg-white px-2 py-0.5 text-xs dark:border-slate-600 dark:bg-slate-900"
      >
        {copied ? "Copied" : "Copy"}
      </button>
    </div>
  );
}

export default function SettingsPage({ onChange }: { onChange: () => void }) {
  const [s, setS] = useState<AssistantStatus | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [message, setMessage] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const load = useCallback(() => {
    api
      .assistant()
      .then(setS)
      .catch((e) => setError(errText(e)));
  }, []);
  useEffect(() => {
    load();
    const t = setInterval(load, 15000); // keep the connection light current
    return () => clearInterval(t);
  }, [load]);

  if (!s) return <Loading error={error} />;

  const run = (p: Promise<AssistantStatus>, ok: (r: AssistantStatus) => string) => {
    setBusy(true);
    setError(null);
    p.then((r) => {
      setS(r);
      setMessage(ok(r));
      onChange();
    })
      .catch((e) => setError(errText(e)))
      .finally(() => setBusy(false));
  };

  const h = hoursOld(s.last_used);
  const light: [string, string] = !s.enabled
    ? ["bg-slate-400", "Switched off"]
    : h !== null && h < 0.25
      ? ["bg-green-500", `Connected — Claude used the app ${formatWhen(s.last_used)}`]
      : s.last_used
        ? ["bg-amber-400", `Last used ${formatWhen(s.last_used)}`]
        : ["bg-slate-400", "Not used yet"];
  const desktopJson = JSON.stringify({ mcpServers: s.server_entry }, null, 2);

  return (
    <div className="space-y-6">
      <SummarySettingsCard />
      <TuningCard onChange={onChange} />
      <section className={card}>
        <div className="mb-3 flex flex-wrap items-center justify-between gap-3">
          <h2 className="font-semibold">AI assistant (optional)</h2>
          <label className="flex items-center gap-2 text-sm">
            <input
              type="checkbox"
              checked={s.enabled}
              disabled={busy}
              onChange={(e) =>
                run(api.setAssistant(e.target.checked), (r) =>
                  r.enabled ? "Assistant switched on." : "Assistant switched off: Claude can't read the app until you switch it back on.",
                )
              }
            />
            On
          </label>
        </div>
        <p className="mb-3 text-sm text-slate-600 dark:text-slate-300">
          Chat about your team in <b>Claude Desktop</b> with your own Claude plan. Claude reads this app's numbers (roster, matchup,
          suggestions, free agents…) through a small local server, <b>read-only</b>: it can't change anything here or on Yahoo. This app
          never calls Claude itself and stores no Claude login. Fantasy Manager must be running while you chat.
        </p>
        <div className="mb-4 flex items-center gap-2 text-sm">
          <span className={`inline-block h-2.5 w-2.5 rounded-full ${light[0]}`} />
          {light[1]}
        </div>

        <h3 className="mb-1 text-sm font-semibold">1. Connect Claude Desktop</h3>
        {s.installed && s.outdated ? (
          <Notice tone="warn">
            Claude Desktop is set up for another copy of this app (probably an older version). Press <b>Update in Claude Desktop</b>,
            then restart Claude Desktop.
          </Notice>
        ) : s.installed ? (
          <Notice tone="ok">
            ✓ Installed in Claude Desktop's settings ({s.config_path}). Restart Claude Desktop if you just installed it, then ask e.g.{" "}
            <i>"Using Fantasy Manager, who should I pick up this week?"</i>
          </Notice>
        ) : s.config_path ? (
          <p className="mb-2 text-sm text-slate-500">Adds the "fantasy-manager" server to Claude Desktop's settings file (a backup is kept next to it). Other settings are untouched.</p>
        ) : (
          <Notice tone="warn">Claude Desktop's settings file wasn't found. Install Claude Desktop and open it once, or add the server by hand (below).</Notice>
        )}
        <div className="mt-2 flex flex-wrap items-center gap-2">
          {!s.installed && s.config_path && (
            <button className={btn} disabled={busy} onClick={() => run(api.installAssistant(), () => "Installed. Quit and reopen Claude Desktop to load it.")}>
              Install in Claude Desktop
            </button>
          )}
          {s.installed && s.outdated && (
            <button className={btn} disabled={busy} onClick={() => run(api.installAssistant(), () => "Updated. Quit and reopen Claude Desktop.")}>
              Update in Claude Desktop
            </button>
          )}
          {s.installed && (
            <button
              className="rounded-md border border-slate-300 px-3 py-1.5 text-sm hover:bg-slate-100 dark:border-slate-700 dark:hover:bg-slate-800"
              disabled={busy}
              onClick={() => run(api.uninstallAssistant(), () => "Removed from Claude Desktop's settings. Restart Claude Desktop.")}
            >
              Remove from Claude Desktop
            </button>
          )}
          <a href="claude://" className="text-sm text-violet-700 hover:underline dark:text-violet-300">
            Open Claude Desktop ↗
          </a>
        </div>
        {message && <p className="mt-2 text-sm text-green-700 dark:text-green-400">{message}</p>}
        {error && <p className="mt-2 text-sm text-red-600 dark:text-red-400">{error}</p>}

        <details className="mt-4 text-sm">
          <summary className="cursor-pointer text-slate-600 dark:text-slate-300">Add it by hand (Claude Desktop → Settings → Developer → Edit Config)</summary>
          <p className="my-2 text-slate-500">Merge this into claude_desktop_config.json, then restart Claude Desktop:</p>
          <CopyBox text={desktopJson} />
        </details>

        <h3 className="mb-1 mt-5 text-sm font-semibold">2. Claude Code (optional)</h3>
        <p className="mb-2 text-sm text-slate-500">Run once in a terminal to add the same read-only tools to Claude Code:</p>
        <CopyBox text={s.claude_code_command} />

        <h3 className="mb-1 mt-5 text-sm font-semibold">What Claude can read</h3>
        <p className="text-sm text-slate-500">
          Teams and data freshness, your roster, the matchup, best lineup, alerts, suggested moves (A–D), free agent search, the
          streaming plan, the move log, trade analysis and trade ideas, the schedule grid, player comparisons, opponent scouting
          and your scoring profile.
        </p>
      </section>
    </div>
  );
}
