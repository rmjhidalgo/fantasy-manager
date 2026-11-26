import { useCallback, useEffect, useState } from "react";
import { api, type AssistantStatus } from "../api";
import { formatWhen, hoursOld } from "../time";
import { btn, card, errText, Loading, Notice } from "../ui";

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
        {s.installed ? (
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
          streaming plan and the move log.
        </p>
      </section>
    </div>
  );
}
