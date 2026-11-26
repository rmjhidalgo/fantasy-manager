import { useEffect, useState } from "react";
import { api, type Scouting } from "../../api";
import { card, errText, Loading, Notice, StatusTag } from "../../ui";

export default function ScoutingPanel() {
  const [d, setD] = useState<Scouting | null>(null);
  const [error, setError] = useState<string | null>(null);
  useEffect(() => {
    api
      .scouting()
      .then(setD)
      .catch((e) => setError(errText(e)));
  }, []);
  if (!d) return <Loading error={error} />;
  if (d.opponents.length === 0) return <Notice>Save your Yahoo Matchup page to scout your opponent.</Notice>;

  return (
    <div className="space-y-4">
      {d.opponents.map((o) => (
        <section key={o.week} className={card}>
          <h2 className="font-semibold">
            Week {o.week} opponent: {o.team.name}
          </h2>
          <p className="mb-3 text-sm text-slate-500">
            {o.team.rank != null && `#${o.team.rank} · `}
            {o.team.record && `${o.team.record} · `}
            {o.team.points_for != null && `${o.team.points_for.toFixed(0)} points for this season · `}
            {o.games_left} games left this week (healthy players)
            {o.adds_this_week != null && ` · ${o.adds_this_week} add${o.adds_this_week !== 1 ? "s" : ""} used this week (seen in transactions)`}
          </p>
          {o.injured.length > 0 && (
            <Notice tone="warn">
              <b>Injury holes:</b>{" "}
              {o.injured.map((r) => `${r.name} (${r.status ?? `missed ${r.missed_streak} games`}${r.on_il ? ", on IL" : ""})`).join(", ")}
            </Notice>
          )}
          <table className="mt-3 w-full text-sm">
            <thead className="text-left text-slate-500">
              <tr>
                <th className="py-1 pr-2 font-medium">Player</th>
                <th className="py-1 pr-2 text-right font-medium">FP/G</th>
                <th className="py-1 text-right font-medium">Games left</th>
              </tr>
            </thead>
            <tbody>
              {o.roster.map((r) => (
                <tr key={r.name} className={`border-t border-slate-100 dark:border-slate-800 ${r.on_il ? "text-slate-400" : ""}`}>
                  <td className="py-1 pr-2">
                    {r.name}
                    <StatusTag status={r.status} />
                    <span className="ml-1 text-xs text-slate-500">
                      {r.nba_team} · {r.positions.join(",")}
                      {r.on_il && " · IL"}
                    </span>
                  </td>
                  <td className="py-1 pr-2 text-right tabular-nums">{r.fpts.toFixed(1)}</td>
                  <td className="py-1 text-right tabular-nums">{r.games_left}</td>
                </tr>
              ))}
            </tbody>
          </table>
          <h3 className="mb-1 mt-4 text-sm font-semibold">Their recent transactions</h3>
          {o.transactions.length === 0 ? (
            <p className="text-sm text-slate-500">None on your last saved League page.</p>
          ) : (
            <ul className="text-sm">
              {o.transactions.map((t, i) => (
                <li key={i}>
                  <span className="text-xs text-slate-500">{t.when}</span> {t.moves.map((m) => `${m.action === "add" ? "+" : "−"}${m.name}`).join("  ")}
                </li>
              ))}
            </ul>
          )}
        </section>
      ))}
      <p className="text-xs text-slate-500">Rosters are as last saved (Taken pages, Matchup page) plus newer transactions.</p>
    </div>
  );
}
