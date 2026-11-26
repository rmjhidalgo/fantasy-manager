import { useCallback, useEffect, useState } from "react";
import { api, type MoveLogData } from "../api";
import { formatWhen } from "../time";
import { card, errText, Loading, YahooLink } from "../ui";

const STATUS: Record<MoveLogData["moves"][number]["status"], [string, string]> = {
  open: ["Waiting for an import", "bg-slate-100 text-slate-700 dark:bg-slate-800 dark:text-slate-300"],
  done: ["Done", "bg-green-100 text-green-800 dark:bg-green-950 dark:text-green-300"],
  missed: ["Missed", "bg-red-100 text-red-700 dark:bg-red-950 dark:text-red-300"],
  "not done": ["Not done", "bg-amber-100 text-amber-800 dark:bg-amber-950 dark:text-amber-300"],
  dismissed: ["Dismissed", "bg-slate-100 text-slate-500 dark:bg-slate-800 dark:text-slate-400"],
};

export default function MovesPage() {
  const [data, setData] = useState<MoveLogData | null>(null);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(() => {
    api
      .moveLog()
      .then((d) => {
        setData(d);
        setError(null);
      })
      .catch((e) => setError(errText(e)));
  }, []);
  useEffect(load, [load]);

  if (!data) return <Loading error={error} />;
  const setStatus = (id: number, s: "open" | "dismissed") => api.setMoveStatus(id, s).then(load).catch((e) => setError(errText(e)));

  return (
    <div className="space-y-6">
      <section className={card}>
        <h2 className="mb-1 font-semibold">Move log</h2>
        <p className="mb-3 text-sm text-slate-500">
          Moves you opened on Yahoo from Suggested moves, Free agents or Streaming. Your next saved Team or League page shows whether
          each one happened.
        </p>
        {data.moves.length === 0 ? (
          <p className="text-sm text-slate-500">Nothing yet: click "Add on Yahoo" on a suggestion and it appears here.</p>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full min-w-[640px] text-sm">
              <thead className="text-left text-slate-500">
                <tr>
                  <th className="py-1 pr-2 font-medium">Opened</th>
                  <th className="py-1 pr-2 font-medium">Move</th>
                  <th className="py-1 pr-2 font-medium">From</th>
                  <th className="py-1 pr-2 text-right font-medium">Gain</th>
                  <th className="py-1 pr-2 font-medium">Result</th>
                  <th className="py-1 font-medium"></th>
                </tr>
              </thead>
              <tbody>
                {data.moves.map((m) => {
                  const [label, tone] = STATUS[m.status];
                  return (
                    <tr key={m.id} className="border-t border-slate-100 align-top dark:border-slate-800">
                      <td className="py-1.5 pr-2 text-xs text-slate-500">{formatWhen(m.created_at)}</td>
                      <td className="py-1.5 pr-2">
                        <span className="text-green-700 dark:text-green-400">+</span> {m.add_name}
                        {m.drop_name && (
                          <>
                            {" "}
                            <span className="text-red-700 dark:text-red-400">−</span> {m.drop_name}
                          </>
                        )}
                      </td>
                      <td className="py-1.5 pr-2 text-xs text-slate-500">
                        {m.source}
                        {m.horizon && ` (${m.horizon})`}
                      </td>
                      <td className="py-1.5 pr-2 text-right tabular-nums">{m.gain != null ? `+${m.gain.toFixed(1)}` : "–"}</td>
                      <td className="py-1.5 pr-2">
                        <span className={`rounded px-1.5 py-0.5 text-xs font-medium ${tone}`}>{label}</span>
                        {m.note && <div className="text-xs text-slate-500">{m.note}</div>}
                      </td>
                      <td className="py-1.5 text-right text-xs">
                        {m.status === "open" && (
                          <>
                            <YahooLink href={m.yahoo_url}>Yahoo ↗</YahooLink>{" "}
                            <button onClick={() => setStatus(m.id, "dismissed")} className="ml-2 text-slate-500 hover:underline">
                              Dismiss
                            </button>
                          </>
                        )}
                        {m.status === "dismissed" && (
                          <button onClick={() => setStatus(m.id, "open")} className="text-slate-500 hover:underline">
                            Reopen
                          </button>
                        )}
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        )}
      </section>

      <section className={card}>
        <h2 className="mb-1 font-semibold">Your recent Yahoo transactions</h2>
        <p className="mb-3 text-sm text-slate-500">From your last saved League page (Yahoo lists only the latest few).</p>
        {data.transactions.length === 0 ? (
          <p className="text-sm text-slate-500">None found. Save the League home page to see them.</p>
        ) : (
          <ul className="space-y-1.5 text-sm">
            {data.transactions.map((t, i) => (
              <li key={i} className="border-t border-slate-100 pt-1.5 first:border-0 first:pt-0 dark:border-slate-800">
                <span className="text-xs text-slate-500">{t.when}</span>{" "}
                {t.moves.length > 0
                  ? t.moves.map((m, j) => (
                      <span key={j} className="mr-3">
                        <span className={m.action === "add" ? "text-green-700 dark:text-green-400" : "text-red-700 dark:text-red-400"}>
                          {m.action === "add" ? "+" : "−"}
                        </span>{" "}
                        {m.name}
                      </span>
                    ))
                  : t.description}
              </li>
            ))}
          </ul>
        )}
      </section>
    </div>
  );
}
